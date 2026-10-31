"""AURA CLI entry point — TUI, Real-Time Telemetry Monitor, and Audit Verification."""
from __future__ import annotations
import sys
import os
import argparse
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="aura",
        description="AURA — Agent Control Plane: Interception, Risk Assessment, and Observability",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  aura                  Launch the interactive TUI application
  aura --monitor        Launch the real-time telemetry and audit monitor dashboard
  aura --verify-audit   Verify cryptographic hash chain integrity of the audit log
  aura --mock           Force offline mock mode (no API keys required)
  aura --check          Run connectivity and provider diagnostics
  aura --version        Show version
        """,
    )
    parser.add_argument("--version", action="version", version="AURA 0.1.0")
    parser.add_argument("--mock", action="store_true", help="Force mock mode for all providers")
    parser.add_argument("--monitor", action="store_true", help="Launch live real-time terminal telemetry monitor")
    parser.add_argument("--verify-audit", action="store_true", help="Verify cryptographic hash chain in audit event log")
    parser.add_argument("--check", action="store_true", help="Perform system diagnostics and health checks")
    parser.add_argument("--no-color", action="store_true", help="Disable color output")
    parser.add_argument("--data-dir", default=None, help="Override data directory")
    args = parser.parse_args()

    if args.mock:
        os.environ["AURA_JEV_MOCK_MODE"] = "true"
    if args.no_color:
        os.environ["AURA_NO_COLOR"] = "true"
    if args.data_dir:
        os.environ["AURA_DATA_DIR"] = args.data_dir

    from aura.config import get_config
    cfg = get_config()

    # 1. Real-time Live Telemetry Monitor Mode
    if args.monitor:
        from aura.ui.realtime_monitor import run_realtime_monitor
        try:
            run_realtime_monitor(refresh_seconds=cfg.display.monitor_refresh_seconds)
        except KeyboardInterrupt:
            print("\nReal-time monitor stopped.")
        return

    # 2. Cryptographic Hash Chain Audit Verification
    if args.verify_audit:
        from aura.observability.hash_chain import verify_audit_log_chain
        from rich.console import Console
        from rich.panel import Panel
        from rich.table import Table

        console = Console()
        events_file = cfg.runtime.data_dir / "logs" / "aura-events.jsonl"
        report = verify_audit_log_chain(events_file)

        table = Table(title="AURA Cryptographic Hash Chain Verification Report", show_header=True)
        table.add_column("Property", style="dim")
        table.add_column("Value")

        status = "[bold green]VALID (100% UNTAMPERED)[/bold green]" if report["valid"] else "[bold red]TAMPER DETECTED / CORRUPTED[/bold red]"
        table.add_row("Integrity Status", status)
        table.add_row("Audited Events Count", str(report["total_events"]))
        table.add_row("Chain Head Hash", f"[cyan]{report['head_hash']}[/cyan]")
        table.add_row("Genesis Anchor", f"[dim]{report['genesis_hash']}[/dim]")

        if report["errors"]:
            table.add_row("Detected Violations", "\n".join(report["errors"][:5]))

        console.print(Panel(table, expand=False))
        sys.exit(0 if report["valid"] else 1)

    # 3. Connectivity & Provider Health Check
    if args.check:
        import asyncio
        from rich.console import Console
        from aura.agent import AURAOrchestrator
        console = Console()
        console.print("[bold cyan]Running AURA Diagnostic Checks...[/bold cyan]")
        orchestrator = AURAOrchestrator(config=cfg)

        async def _check():
            agent_ok = await orchestrator.health_check_provider()
            jev_ok = await orchestrator.health_check_jev()
            console.print(f"Agent Provider ({cfg.llm.provider}): {'[green]CONNECTED[/green]' if agent_ok else '[yellow]MOCK/OFFLINE[/yellow]'}")
            console.print(f"JEV Engine ({'MOCK' if cfg.jev.mock_mode else cfg.jev.provider}): {'[green]CONNECTED[/green]' if jev_ok else '[red]FAILED[/red]'}")
            console.print(f"Database Path: [cyan]{cfg.runtime.data_dir / 'employees.db'}[/cyan]")
            console.print(f"Audit Log: [cyan]{cfg.runtime.data_dir / 'logs' / 'aura-events.jsonl'}[/cyan]")

        asyncio.run(_check())
        return

    # 4. Interactive TUI Application
    try:
        from aura.app import AURAApp
        app = AURAApp()
        app.run()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"\nAURA UI startup error: {e}", file=sys.stderr)
        print("Tip: Run 'aura --monitor' for the standalone real-time terminal monitor.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
