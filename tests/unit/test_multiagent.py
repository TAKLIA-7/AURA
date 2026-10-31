"""Unit tests for AURA LangGraph Multi-Agent Architecture and Governance."""
import os
import pytest
from pathlib import Path
from aura.sdk.interceptor import AuraGovernor
from aura.multiagent.graph import build_multiagent_graph
from aura.multiagent.orchestrator import MultiAgentOrchestrator


@pytest.fixture
def multi_governor(tmp_path: Path) -> AuraGovernor:
    os.environ["AURA_TEST_MOCK_LLM"] = "true"
    return AuraGovernor(workspace_root=tmp_path, data_dir=tmp_path)


@pytest.mark.asyncio
async def test_multiagent_graph_execution(multi_governor: AuraGovernor):
    # Build LangGraph
    app = build_multiagent_graph(governor=multi_governor)

    initial_state = {
        "messages": [],
        "user_intent": "List all departments and their budgets",
        "current_agent": "supervisor",
        "next_agent": "supervisor",
        "org_id": "default-org",
        "user_role": "analyst",
        "sql_query": None,
        "sql_result": None,
        "rag_context": [],
        "analysis_result": None,
        "action_trace": [],
        "final_output": None,
    }

    config = {"configurable": {"thread_id": "test_thread_001"}}
    final_state = await app.ainvoke(initial_state, config=config)

    assert final_state is not None
    assert final_state["current_agent"] == "analyst_agent"
    assert len(final_state["action_trace"]) >= 1
    assert final_state["final_output"] is not None


@pytest.mark.asyncio
async def test_multiagent_orchestrator_streaming(multi_governor: AuraGovernor):
    orchestrator = MultiAgentOrchestrator(governor=multi_governor)
    messages = []
    # Admin has access to salary protected resource without waiting for approval
    async for msg in orchestrator.run("Show top 5 employees by salary", role="admin"):
        messages.append(msg)

    kinds = [m.kind for m in messages]
    assert "run_started" in kinds
    assert "agent_text" in kinds
    assert "run_completed" in kinds


@pytest.mark.asyncio
async def test_multiagent_intercepts_approval(multi_governor: AuraGovernor):
    # Set on_approval_needed callback to auto-approve in test
    async def auto_approve(info):
        await multi_governor.approval_mgr.resolve(info["approval_id"], "approved")

    multi_governor.on_approval_needed = auto_approve

    orchestrator = MultiAgentOrchestrator(governor=multi_governor)
    messages = []
    # Analyst queries protected salary -> triggers approval gate -> auto-approves
    async for msg in orchestrator.run("Show top 5 employees by salary", role="analyst"):
        messages.append(msg)

    kinds = [m.kind for m in messages]
    assert "run_started" in kinds
    assert "run_completed" in kinds
