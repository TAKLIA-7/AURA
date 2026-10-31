"""AURA SDK — Reusable tool interception, LangChain adapter, and governance wrapper."""
from __future__ import annotations
import asyncio
import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from aura.config import AURAConfig
from aura.models import (
    ActionRequest, ActionResult, DecisionResult,
    EventLevel, AuditEvent, RunRecord, RunStatus,
)
from aura.gateway import ToolRegistry, ToolExecutor
from aura.policies import PolicyEngine, ApprovalManager
from aura.governance import GovernanceManager
from aura.rag import PineconeRAGService
from aura.jev import JEVClient, JEVContextBuilder, MockJEVClient, OpenRouterJEVClient
from aura.observability import get_event_bus, get_run_repo, JSONLLogger


class AuraGovernor:
    """
    Central governance engine that intercepts and evaluates any tool action
    across LangGraph, LangChain, MCP, or custom agents.
    Sub-agents NEVER execute tools directly; all calls must flow through AuraGovernor.
    """

    def __init__(
        self,
        config: Optional[AURAConfig] = None,
        workspace_root: Optional[Path] = None,
        data_dir: Optional[Path] = None,
        on_approval_needed: Optional[Callable] = None,
    ) -> None:
        self.config = config or AURAConfig.from_env()
        self.workspace_root = workspace_root or self.config.runtime.workspace_root
        self.data_dir = data_dir or self.config.runtime.data_dir

        self.registry = ToolRegistry(self.workspace_root)
        self.executor = ToolExecutor(self.registry)
        self.governance_mgr = GovernanceManager(self.data_dir / "governance.db")
        self.policy_engine = PolicyEngine(self.workspace_root, governance_manager=self.governance_mgr)
        self.approval_mgr = ApprovalManager()
        self.rag_service = PineconeRAGService()
        self.context_builder = JEVContextBuilder()
        self.on_approval_needed = on_approval_needed

        # JEV setup
        if not self.config.jev.mock_mode and self.config.jev.api_key and not os.getenv("AURA_TEST_MOCK_LLM"):
            self.jev_client = OpenRouterJEVClient(
                api_key=self.config.jev.api_key,
                model=self.config.jev.model,
                base_url=self.config.jev.endpoint or "https://openrouter.ai/api/v1",
                timeout=self.config.jev.timeout_seconds,
            )
        else:
            self.jev_client = MockJEVClient()

        self.event_bus = get_event_bus()
        self.run_repo = get_run_repo()
        self.jsonl_logger = JSONLLogger(self.data_dir / "logs")

    async def execute_governed_action(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        user_intent: str = "Multi-agent autonomous task",
        org_id: str = "default-org",
        role: str = "analyst",
        session_id: str = "session_sdk",
        run_id: str = "run_sdk",
    ) -> ActionResult:
        """
        Executes the full AURA Governance Pipeline:
        1. Request Enrichment
        2. Deterministic Pre-assessment Check (Allowlist, Path traversal, Org policies)
        3. Fast-Path Check
        4. Pinecone Policy Retrieval
        5. JEV Risk Assessment
        6. Human Approval Gate
        7. Tool Execution & Audit Logging
        """
        request = ActionRequest(
            tool=tool_name,
            arguments=arguments,
            target=str(arguments.get("path") or arguments.get("target") or ""),
            org_id=org_id,
            role=role,
        )
        request = self.registry.enrich_request(request)

        # 1. Deterministic pre-checks (Security Invariants & Org Policies)
        pre_decision = self.policy_engine.pre_assessment_check(request)
        if pre_decision and pre_decision.decision == DecisionResult.BLOCK:
            await self._log_event(
                EventLevel.WARNING, "aura.action.blocked",
                session_id, run_id, request.request_id, tool_name,
                {"reason": pre_decision.reason, "rule": pre_decision.policy_rule_id},
            )
            return ActionResult(
                request_id=request.request_id,
                success=False,
                error=f"AURA GOVERNANCE BLOCK: {pre_decision.reason}",
            )

        # 2. Fast-Path Check (safe diagnostic tools skip JEV)
        if self.policy_engine.fast_allow(request):
            return await self.executor.execute(request)

        # 3. Determine if deterministic approval is required
        final_decision = None
        assessment = None
        if pre_decision and pre_decision.decision == DecisionResult.APPROVAL_REQUIRED:
            final_decision = pre_decision
        else:
            # 4. Pinecone RAG policy retrieval for JEV
            rag_context = self.rag_service.get_policy_context_for_action(
                user_intent=user_intent,
                tool_name=tool_name,
                org_id=org_id,
            )
            dummy_run = RunRecord(session_id=session_id, user_prompt=user_intent)
            dummy_run.run_id = run_id
            jev_payload = self.context_builder.build(
                request=request,
                user_intent=user_intent,
                run=dummy_run,
                policy_context=rag_context or None,
            )

            # 5. JEV Risk Assessment
            try:
                assessment = await asyncio.wait_for(
                    self.jev_client.assess(jev_payload),
                    timeout=self.config.jev.timeout_seconds,
                )
                final_decision = self.policy_engine.apply_jev_assessment(request, assessment)
            except Exception as e:
                # Fail closed on JEV failure
                final_decision = PolicyDecision(
                    request_id=request.request_id,
                    decision=DecisionResult.APPROVAL_REQUIRED,
                    reason=f"JEV assessment error: {e}",
                    policy_rule_id="POLICY-JEV-ERROR",
                    requires_human_review=True,
                    enforced=False,
                )

        # 6. Enforcement
        if final_decision.decision == DecisionResult.BLOCK:
            await self._log_event(
                EventLevel.WARNING, "aura.action.blocked",
                session_id, run_id, request.request_id, tool_name,
                {"reason": final_decision.reason},
            )
            return ActionResult(
                request_id=request.request_id,
                success=False,
                error=f"AURA POLICY BLOCK: {final_decision.reason}",
            )

        if final_decision.decision == DecisionResult.APPROVAL_REQUIRED:
            approval_id = await self.approval_mgr.request_approval(request, final_decision, assessment)
            if self.on_approval_needed:
                cb_res = self.on_approval_needed({
                    "approval_id": approval_id,
                    "tool": tool_name,
                    "arguments": arguments,
                    "reason": final_decision.reason,
                })
                if asyncio.iscoroutine(cb_res):
                    await cb_res
            resolution = await self.approval_mgr.wait_for_resolution(approval_id, timeout=120.0)
            if resolution != "approved":
                return ActionResult(
                    request_id=request.request_id,
                    success=False,
                    error=f"AURA ACTION DENIED BY OPERATOR ({resolution})",
                )

        # 7. Execute tool safely through ToolExecutor
        result = await self.executor.execute(request)
        await self._log_event(
            EventLevel.INFO if result.success else EventLevel.ERROR,
            "aura.action.executed" if result.success else "aura.action.failed",
            session_id, run_id, request.request_id, tool_name,
            {"success": result.success, "duration_ms": result.duration_ms},
        )
        return result

    async def _log_event(self, level: EventLevel, event_type: str, session_id: str, run_id: str, req_id: str, tool: str, metadata: dict):
        event = AuditEvent(
            level=level,
            event_type=event_type,
            session_id=session_id,
            run_id=run_id,
            request_id=req_id,
            action={"tool": tool},
            metadata=metadata,
        )
        await self.event_bus.emit(event)
        await self.jsonl_logger.log(event)


# ── LangChain Reusable Adapter ────────────────────────────────────────────────

try:
    from langchain_core.tools import BaseTool
    from pydantic import Field

    class AuraLangChainTool(BaseTool):
        """
        Wraps any tool so calls from LangGraph/LangChain agents are strictly intercepted
        and validated by AURA governance before execution.
        """
        name: str
        description: str
        governor: AuraGovernor
        user_intent: str = "LangChain Agent Execution"
        org_id: str = "default-org"
        role: str = "analyst"

        def _run(self, *args: Any, **kwargs: Any) -> str:
            # Synchronous bridge for LangChain
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(asyncio.run, self._arun(*args, **kwargs))
                    return future.result()
            return asyncio.run(self._arun(*args, **kwargs))

        async def _arun(self, *args: Any, **kwargs: Any) -> str:
            # Merge positional or dict arguments
            arguments = dict(kwargs)
            if args and isinstance(args[0], dict):
                arguments.update(args[0])
            elif args:
                arguments["input"] = args[0]

            result = await self.governor.execute_governed_action(
                tool_name=self.name,
                arguments=arguments,
                user_intent=self.user_intent,
                org_id=self.org_id,
                role=self.role,
            )
            if not result.success:
                return f"[AURA GOVERNANCE ERROR]: {result.error}"
            import json
            if isinstance(result.output, (dict, list)):
                return json.dumps(result.output)
            return str(result.output)

except ImportError:
    pass
