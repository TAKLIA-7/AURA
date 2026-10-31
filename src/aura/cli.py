"""AURA CLI entry point — Interactive TUI, Multi-Agent Governor, MCP Server, and Policy Manager."""
from __future__ import annotations
import sys
import os
import asyncio
import argparse
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="aura",
        description="AURA — Multi-Agent AI Governance Platform: Control Plane, Risk Assessment, and Observability",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  aura                                  Launch the interactive TUI
  aura --multiagent "Show departments"  Execute prompt using LangGraph multi-agent governance
  aura --policies                       List active organizational policies and roles
  aura --mcp                            Launch Model Context Protocol (MCP) JSON-RPC server
  aura --mock                           Force mock mode (no API keys needed)
  aura --version                        Show version
        """,
    )
    parser.add_argument("--version", action="version", version="AURA 0.2.0 (Multi-Agent Governance)")
    parser.add_argument("--mock", action="store_true", help="Force mock mode for all providers")
    parser.add_argument("--no-color", action="store_true", help="Disable color output")
    parser.add_argument("--data-dir", default=None, help="Override data directory")
    parser.add_argument("--multiagent", nargs="?", const="default", help="Run with LangGraph multi-agent governor")
    parser.add_argument("--model", "-m", default=None, help="Select model alias (A, B, C, D, gemini) or model slug")
    parser.add_argument("--list-models", action="store_true", help="List available switchable model aliases")
    parser.add_argument("--policies", action="store_true", help="Display active organizational policies from SQLite")
    parser.add_argument("--mcp", action="store_true", help="Run as Model Context Protocol (MCP) server")
    parser.add_argument("--ingest", nargs=2, metavar=("FILE", "TITLE"), help="Ingest a policy document into Pinecone RAG")
    args = parser.parse_args()

    if args.list_models:
        from aura.multiagent.llm_factory import MODELS
        print("\n=== AURA Switchable Model Registry ===")
        for key, slug in MODELS.items():
            print(f"  [{key}] -> {slug}")
        print("\nUsage:")
        print("  aura --model A --multiagent \"prompt\"")
        print("  or set MODEL=A in your .env file\n")
        sys.exit(0)

    if args.mock:
        os.environ["AURA_JEV_MOCK_MODE"] = "true"
        os.environ["AURA_TEST_MOCK_LLM"] = "true"
    if args.no_color:
        os.environ["AURA_NO_COLOR"] = "true"
    if args.data_dir:
        os.environ["AURA_DATA_DIR"] = args.data_dir
    if args.model:
        os.environ["AURA_MODEL"] = args.model


    # 1. Policies CLI Inspector
    if args.policies:
        from aura.governance import GovernanceManager
        gm = GovernanceManager()
        org = gm.get_organization("default-org")
        print(f"\n=== AURA ORGANIZATIONAL GOVERNANCE ===")
        print(f"Organization: {org['name']} (ID: {org['org_id']})\n")
        print(f"Active Policies:")
        for pol in gm.get_active_policies("default-org"):
            print(f"  - {pol.name} (v{pol.version})")
            print(f"    Description: {pol.description}")
            print(f"    Protected Resources: {', '.join(pol.protected_resources)}")
            print(f"    Required Approvals: {', '.join(pol.required_approval_roles)}\n")
        sys.exit(0)

    # 2. Ingest Document CLI
    if args.ingest:
        file_path, title = args.ingest
        p = Path(file_path)
        if not p.exists():
            print(f"Error: File not found: {file_path}", file=sys.stderr)
            sys.exit(1)
        from aura.rag import PineconeRAGService
        rag = PineconeRAGService()
        content = p.read_text(encoding="utf-8")
        doc_id = f"doc_{p.stem}"
        res = rag.ingest_policy_document(doc_id=doc_id, title=title, content=content)
        print(f"Successfully ingested '{title}' into Pinecone RAG ({res['chunks_ingested']} chunks).")
        sys.exit(0)

    # 3. Model Context Protocol (MCP) Server
    if args.mcp:
        from aura.mcp.server import AuraMCPServer
        mcp = AuraMCPServer()
        print("AURA MCP Server listening on stdio (JSON-RPC)...", file=sys.stderr)
        async def run_mcp_stdio():
            for line in sys.stdin:
                line = line.strip()
                if line:
                    res = await mcp.handle_json_rpc(line)
                    sys.stdout.write(res + "\n")
                    sys.stdout.flush()
        asyncio.run(run_mcp_stdio())
        sys.exit(0)

    # 4. Multi-Agent CLI Mode
    if args.multiagent:
        prompt = args.multiagent if args.multiagent != "default" else "List departments and top salaries"
        from aura.multiagent.orchestrator import MultiAgentOrchestrator
        from aura.multiagent.llm_factory import resolve_model_name
        model_selection = args.model or os.getenv("MODEL") or os.getenv("OPENROUTER_MODEL")
        orchestrator = MultiAgentOrchestrator(model_name=model_selection)
        resolved = resolve_model_name(model_selection)
        print(f"\n=== AURA Multi-Agent Governance Execution ===")
        print(f"Active Model: {resolved} (Alias/Key: {model_selection or 'default'})")
        print(f"Prompt: {prompt}\n")

        async def run_cli():
            async for msg in orchestrator.run(prompt):
                if msg.kind == "agent_thought":
                    print(f"[*] {msg.content}")
                elif msg.kind == "agent_text":
                    print(f"\n{msg.content}\n")
                elif msg.kind == "action_executed":
                    print(f"  [OK] Tool Executed: {msg.content.get('tool')}")
                elif msg.kind == "action_blocked":
                    print(f"  [BLOCKED] Action Blocked: {msg.content.get('tool')} ({msg.content.get('reason')})")
                elif msg.kind == "run_completed":
                    print(f"\n=== Run Completed (ID: {msg.content.get('run_id')}) ===")
        asyncio.run(run_cli())
        sys.exit(0)

    # 5. Default: Interactive TUI
    try:
        from aura.app import AURAApp
        app = AURAApp()
        app.run()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"\nAURA startup error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
