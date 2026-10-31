"""AURA Multi-Agent Orchestrator — Bridges LangGraph with AURA Observability & TUI."""
from __future__ import annotations
import uuid
from typing import Any, AsyncGenerator, Dict, List, Optional
from langchain_core.messages import HumanMessage
from aura.agent import AgentMessage
from aura.models import AuditEvent, EventLevel, RunRecord, RunStatus
from aura.observability import get_event_bus, get_run_repo
from aura.multiagent.graph import build_multiagent_graph
from aura.sdk.interceptor import AuraGovernor


class MultiAgentOrchestrator:
    """
    Orchestrates the LangGraph multi-agent team while maintaining complete
    compatibility with AURA's event bus, runs repository, and TUI.
    """

    def __init__(self, governor: Optional[AuraGovernor] = None, model_name: Optional[str] = None) -> None:
        self.governor = governor or AuraGovernor()
        self.model_name = model_name
        self.app = build_multiagent_graph(governor=self.governor, model_name=model_name)
        self.event_bus = get_event_bus()
        self.run_repo = get_run_repo()
        self.session_id = f"session_multi_{uuid.uuid4().hex[:8]}"

    async def run(
        self,
        prompt: str,
        org_id: str = "default-org",
        role: str = "analyst",
    ) -> AsyncGenerator[AgentMessage, None]:
        """Runs the multi-agent graph and yields streaming AgentMessages."""
        from aura.multiagent.llm_factory import resolve_model_name
        active_model = resolve_model_name(self.model_name)
        run = RunRecord(
            session_id=self.session_id,
            user_prompt=prompt,
            provider="langgraph-multiagent",
            model=active_model,
        )
        await self.run_repo.save(run)


        await self.event_bus.emit(AuditEvent(
            level=EventLevel.INFO,
            event_type="aura.multiagent.started",
            session_id=self.session_id,
            run_id=run.run_id,
            actor={"type": "multiagent_supervisor"},
            metadata={"org_id": org_id, "role": role, "prompt": prompt},
        ))
        yield AgentMessage("run_started", {"run_id": run.run_id})

        initial_state = {
            "messages": [HumanMessage(content=prompt)],
            "user_intent": prompt,
            "current_agent": "supervisor",
            "next_agent": "supervisor",
            "org_id": org_id,
            "user_role": role,
            "sql_query": None,
            "sql_result": None,
            "rag_context": [],
            "analysis_result": None,
            "action_trace": [],
            "final_output": None,
        }

        config = {"configurable": {"thread_id": run.run_id}}
        final_text = ""

        try:
            # Stream nodes in the graph
            async for step in self.app.astream(initial_state, config=config):
                for node_name, output in step.items():
                    yield AgentMessage("agent_thought", f"[{node_name.upper()}]: Active turn")

                    # Check for messages
                    if "messages" in output and output["messages"]:
                        msg_text = output["messages"][-1].content
                        yield AgentMessage("agent_text", f"[{node_name}]: {msg_text}")
                        if node_name == "analyst_agent" or "final_output" in output:
                            final_text = output.get("final_output") or msg_text

                    # Check for tool action traces
                    if "action_trace" in output and output["action_trace"]:
                        latest_action = output["action_trace"][-1]
                        if latest_action.get("success") is False:
                            run.blocked_actions += 1
                            yield AgentMessage("action_blocked", {
                                "tool": latest_action.get("tool", "unknown"),
                                "reason": latest_action.get("error", "Blocked by governance policy"),
                            })
                        elif latest_action.get("success") is True:
                            run.allowed_actions += 1
                            yield AgentMessage("action_executed", {
                                "tool": latest_action.get("tool", "unknown"),
                                "success": True,
                            })

            run.status = RunStatus.COMPLETED
            await self.run_repo.update_status(run.run_id, RunStatus.COMPLETED)
            await self.event_bus.emit(AuditEvent(
                level=EventLevel.INFO,
                event_type="aura.multiagent.completed",
                session_id=self.session_id,
                run_id=run.run_id,
                metadata={"final_output": final_text[:200]},
            ))

            yield AgentMessage("run_completed", {
                "run_id": run.run_id,
                "status": "completed",
                "final_text": final_text,
            })

        except Exception as e:
            run.status = RunStatus.FAILED
            await self.run_repo.update_status(run.run_id, RunStatus.FAILED, error=str(e))
            yield AgentMessage("run_failed", {"error": str(e), "run_id": run.run_id})
