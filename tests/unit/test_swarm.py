"""Unit tests for AURA Multi-Agent Swarm Runtime."""
import pytest
from aura.config import AURAConfig
from aura.agent import AURAOrchestrator, AgentMessage
from aura.agent.swarm import SwarmCoordinator, SwarmMember, STANDARD_SWARM_ROSTER
from aura.models import AgentRole, ActionRequest, DecisionResult


@pytest.fixture
def orchestrator():
    cfg = AURAConfig.from_env()
    return AURAOrchestrator(config=cfg)


def test_swarm_roster_initialization(orchestrator):
    """Verify that all specialized swarm members are initialized and registered."""
    swarm = orchestrator.swarm_coordinator
    members = swarm.get_members()
    assert len(members) >= 4

    member_ids = {m.agent_id for m in members}
    assert "supervisor" in member_ids
    assert "sql_agent" in member_ids
    assert "fs_agent" in member_ids
    assert "security_agent" in member_ids

    # Verify roles
    assert swarm.get_member("supervisor").role == AgentRole.SUPERVISOR
    assert swarm.get_member("sql_agent").role == AgentRole.SQL_AGENT
    assert swarm.get_member("fs_agent").role == AgentRole.FS_AGENT
    assert swarm.get_member("security_agent").role == AgentRole.DIAGNOSTIC_AGENT


def test_swarm_monotonic_delegation_valid(orchestrator):
    """Supervisor can delegate to specialized child agents under monotonic attenuation."""
    swarm = orchestrator.swarm_coordinator

    # Supervisor -> SQL Agent: Valid
    valid, reason = swarm.verify_delegation("supervisor", "sql_agent")
    assert valid is True
    assert "attenuation" in reason.lower()

    # Supervisor -> FS Agent: Valid
    valid_fs, reason_fs = swarm.verify_delegation("supervisor", "fs_agent")
    assert valid_fs is True

    # Supervisor -> Security Agent: Valid
    valid_sec, reason_sec = swarm.verify_delegation("supervisor", "security_agent")
    assert valid_sec is True


def test_swarm_privilege_escalation_blocked(orchestrator):
    """Non-supervisor child agents cannot delegate (Priv(Child) <= Priv(Parent))."""
    swarm = orchestrator.swarm_coordinator

    # SQL Agent cannot delegate to supervisor
    valid, reason = swarm.verify_delegation("sql_agent", "supervisor")
    assert valid is False
    assert "not permitted to delegate" in reason.lower()

    # FS Agent cannot delegate
    valid_fs, reason_fs = swarm.verify_delegation("fs_agent", "security_agent")
    assert valid_fs is False


def test_swarm_rbac_tool_enforcement(orchestrator):
    """Child agents are strictly bounded by their assigned tool allowlist."""
    rbac = orchestrator.rbac_manager

    # SQL Agent allowed to query database
    req_sql = ActionRequest(
        tool="sqlite_query",
        operation="query",
        arguments={"query": "SELECT COUNT(*) FROM employees"},
        agent_id="sql_agent",
        agent_role="sql_agent",
    )
    allowed, msg = rbac.is_action_allowed(req_sql)
    assert allowed is True

    # SQL Agent forbidden from executing shell commands
    req_shell = ActionRequest(
        tool="shell.execute",
        operation="execute",
        arguments={"command": "whoami"},
        agent_id="sql_agent",
        agent_role="sql_agent",
    )
    allowed_shell, msg_shell = rbac.is_action_allowed(req_shell)
    assert allowed_shell is False
    assert "not authorized" in msg_shell.lower()

    # FS Agent forbidden from running database queries
    req_fs_sql = ActionRequest(
        tool="sqlite_query",
        operation="query",
        arguments={"query": "SELECT * FROM employees"},
        agent_id="fs_agent",
        agent_role="fs_agent",
    )
    allowed_fs_sql, msg_fs_sql = rbac.is_action_allowed(req_fs_sql)
    assert allowed_fs_sql is False


def test_swarm_direct_addressing(orchestrator):
    """Verify parsing of direct agent addressing syntax (@agent_name)."""
    swarm = orchestrator.swarm_coordinator

    target, prompt = swarm.parse_direct_address("@sql_agent Find top salaries")
    assert target == "sql_agent"
    assert prompt == "Find top salaries"

    target_sec, prompt_sec = swarm.parse_direct_address("@security_agent: check system health")
    assert target_sec == "security_agent"
    assert prompt_sec == "check system health"

    target_none, prompt_none = swarm.parse_direct_address("General question without direct agent")
    assert target_none is None
    assert prompt_none == "General question without direct agent"


def test_swarm_workflow_planning(orchestrator):
    """Verify workflow task decomposition into domain-specific subtasks."""
    swarm = orchestrator.swarm_coordinator

    # Single domain (SQL)
    plan_sql = swarm.plan_swarm_workflow("Count employees by department")
    assert len(plan_sql) >= 1
    assert any(step["agent_id"] == "sql_agent" for step in plan_sql)

    # Multi-domain (SQL + Audit security)
    plan_multi = swarm.plan_swarm_workflow("Count employees and verify cryptographic audit hash chain")
    agent_ids = {s["agent_id"] for s in plan_multi}
    assert "sql_agent" in agent_ids
    assert "security_agent" in agent_ids


@pytest.mark.asyncio
async def test_swarm_execution_flow(orchestrator):
    """End-to-end swarm execution verifies delegation and handoff events."""
    messages = []
    async for msg in orchestrator.run_swarm("How many employees in Engineering department?"):
        messages.append(msg)

    kinds = [m.kind for m in messages]
    assert "agent_text" in kinds
    # When delegating to sql_agent
    assert "agent_delegation" in kinds
    assert "agent_handoff" in kinds

    # Verify delegation content
    delegation_msg = next(m for m in messages if m.kind == "agent_delegation")
    assert delegation_msg.metadata["from_agent"] == "supervisor"
    assert delegation_msg.metadata["to_agent"] == "sql_agent"

