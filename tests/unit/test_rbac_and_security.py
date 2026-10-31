"""Unit tests for AURA Multi-Agent RBAC, Cryptographic Hash Chaining, Idempotency, and Monotone Policy."""
import asyncio
import json
import pytest
from datetime import datetime, timezone, timedelta
from pathlib import Path

from aura.models import (
    ActionRequest, ActionResult, AgentIdentity, AgentRole,
    AuditEvent, DecisionResult, EventLevel, RiskLevel,
)
from aura.policies.rbac import AgentRBACManager, AgentRBACRule, DEFAULT_ROLE_DEFINITIONS
from aura.policies.monotone import MonotonePolicyEngine, MonotonePolicyRule
from aura.policies import PolicyEngine
from aura.gateway.idempotency import IdempotencyManager
from aura.observability.hash_chain import (
    GENESIS_HASH, compute_event_hash, verify_audit_log_chain,
)
from aura.observability import JSONLLogger
from aura.database import run_sqlite_query, validate_sql_security


# ── 1. RBAC Tests ─────────────────────────────────────────────────────────────

def test_rbac_sql_agent_can_query_db(tmp_path):
    rbac = AgentRBACManager()
    agent = AgentIdentity(agent_id="sql_worker_1", role=AgentRole.SQL_AGENT)
    rbac.register_agent(agent)

    req = ActionRequest(
        tool="sqlite.query",
        operation="query",
        agent_id="sql_worker_1",
        arguments={"query": "SELECT * FROM employees;"},
    )
    allowed, reason = rbac.is_action_allowed(req)
    assert allowed is True


def test_rbac_sql_agent_blocked_from_shell_and_fs():
    rbac = AgentRBACManager()
    agent = AgentIdentity(agent_id="sql_worker_2", role=AgentRole.SQL_AGENT)
    rbac.register_agent(agent)

    # Attempt shell execution
    req_shell = ActionRequest(
        tool="shell.execute",
        operation="execute",
        agent_id="sql_worker_2",
        arguments={"command": "whoami"},
    )
    allowed, reason = rbac.is_action_allowed(req_shell)
    assert allowed is False
    assert "not authorized" in reason

    # Attempt file write
    req_write = ActionRequest(
        tool="filesystem.write",
        operation="write",
        agent_id="sql_worker_2",
        arguments={"path": "test.txt", "content": "data"},
    )
    allowed, reason = rbac.is_action_allowed(req_write)
    assert allowed is False


def test_rbac_ttl_token_expiry():
    rbac = AgentRBACManager()
    # Create an agent whose token expired 10 seconds ago
    expired_time = datetime.now(timezone.utc) - timedelta(seconds=20)
    agent = AgentIdentity(
        agent_id="ephemeral_worker",
        role=AgentRole.GENERAL,
        ttl_seconds=5,
        created_at=expired_time,
    )
    rbac.register_agent(agent)

    req = ActionRequest(
        tool="diagnostic.ping",
        operation="ping",
        agent_id="ephemeral_worker",
    )
    allowed, reason = rbac.is_action_allowed(req)
    assert allowed is False
    assert "expired" in reason.lower()


def test_rbac_delegation_attenuation():
    rbac = AgentRBACManager()

    # Supervisor delegating to SQL agent (valid subset)
    valid, msg = rbac.verify_delegation(
        parent_role=AgentRole.SUPERVISOR,
        child_role=AgentRole.SQL_AGENT,
        requested_tools=["sqlite.query"],
    )
    assert valid is True

    # Supervisor attempting to delegate Admin role with mutation (invalid elevation)
    invalid, msg = rbac.verify_delegation(
        parent_role=AgentRole.SUPERVISOR,
        child_role=AgentRole.ADMIN,
    )
    assert invalid is False
    assert "attenuation violation" in msg.lower()


# ── 2. Cryptographic Hash Chain Tests ─────────────────────────────────────────

def test_hash_chain_sequential_integrity(tmp_path):
    log_dir = tmp_path / "logs"
    logger = JSONLLogger(log_dir)

    async def _run_logging():
        e1 = AuditEvent(event_type="aura.test.step1", session_id="sess_1")
        await logger.log(e1)
        e2 = AuditEvent(event_type="aura.test.step2", session_id="sess_1")
        await logger.log(e2)
        e3 = AuditEvent(event_type="aura.test.step3", session_id="sess_1")
        await logger.log(e3)

    asyncio.run(_run_logging())

    # Verify untampered log
    report = logger.verify_integrity()
    assert report["valid"] is True
    assert report["total_events"] == 3
    assert report["errors"] == []
    assert report["head_hash"] != GENESIS_HASH


def test_hash_chain_tamper_detection(tmp_path):
    log_dir = tmp_path / "logs"
    logger = JSONLLogger(log_dir)

    async def _run_logging():
        for i in range(4):
            evt = AuditEvent(event_type=f"aura.test.{i}", session_id="sess_tamper")
            await logger.log(evt)

    asyncio.run(_run_logging())

    # Read lines and tamper with line 2 (index 1)
    events_file = log_dir / "aura-events.jsonl"
    with open(events_file, "r", encoding="utf-8") as f:
        lines = f.readlines()

    tampered_obj = json.loads(lines[1])
    tampered_obj["event_type"] = "aura.tampered.malicious_action"
    lines[1] = json.dumps(tampered_obj) + "\n"

    with open(events_file, "w", encoding="utf-8") as f:
        f.writelines(lines)

    # Verification must detect the tamper
    report = logger.verify_integrity()
    assert report["valid"] is False
    assert len(report["errors"]) > 0
    assert any("tamper detected" in err.lower() or "chain broken" in err.lower() for err in report["errors"])


# ── 3. Idempotency & Race Condition Tests ─────────────────────────────────────

def test_idempotency_caching_and_in_flight():
    async def _test():
        mgr = IdempotencyManager(default_ttl_seconds=60.0)
        req = ActionRequest(
            tool="sqlite.query",
            arguments={"query": "SELECT * FROM departments;"},
            agent_id="test_agent",
        )

        # 1. First arrival reserves slot
        key, cached, in_flight = await mgr.check_and_reserve(req)
        assert cached is None
        assert in_flight is False

        # 2. Concurrent duplicate arrival while in-flight
        key2, cached2, in_flight2 = await mgr.check_and_reserve(req)
        assert cached2 is None
        assert in_flight2 is True  # Race condition detected!

        # 3. Simulate completion of execution
        result = ActionResult(
            request_id=req.request_id,
            success=True,
            output={"count": 5},
            duration_ms=12.5,
        )
        await mgr.record_completion(key, result)

        # 4. Third arrival after completion receives cached result
        key3, cached3, in_flight3 = await mgr.check_and_reserve(req)
        assert cached3 is not None
        assert cached3.idempotent_cached is True
        assert cached3.output == {"count": 5}
        assert in_flight3 is False

    asyncio.run(_test())


def test_rate_limiting_sliding_window():
    mgr = IdempotencyManager()
    agent_id = "flooding_attacker"

    # Allow up to 5 requests in a 10s window
    for i in range(5):
        allowed, msg = mgr.check_rate_limit(agent_id, max_requests=5, window_seconds=10.0)
        assert allowed is True

    # 6th request must exceed rate limit
    blocked, msg = mgr.check_rate_limit(agent_id, max_requests=5, window_seconds=10.0)
    assert blocked is False
    assert "rate limit exceeded" in msg.lower()


# ── 4. Monotone Policy Tests ──────────────────────────────────────────────────

def test_monotone_policy_latches_block(tmp_path):
    engine = MonotonePolicyEngine()
    req = ActionRequest(tool="shell.execute", target="rm -rf /")

    # Initially no constraint
    assert engine.check_monotonic_constraint(req) is None

    # Register a BLOCK decision
    engine.register_decision(req, DecisionResult.BLOCK)

    # Subsequent attempt to access the same target in this context must be blocked by Monotone Policy
    violating = engine.check_monotonic_constraint(req)
    assert violating is not None
    assert violating.decision == DecisionResult.BLOCK
    assert "monotone policy" in violating.reason.lower()


def test_monotone_policy_escalation_lattice():
    engine = MonotonePolicyEngine()
    req = ActionRequest(tool="filesystem.write", target="sensitive.conf")

    # Register APPROVAL_REQUIRED
    engine.register_decision(req, DecisionResult.APPROVAL_REQUIRED)
    d1 = engine.check_monotonic_constraint(req)
    assert d1.decision == DecisionResult.APPROVAL_REQUIRED

    # Escalating to BLOCK moves floor up
    engine.register_decision(req, DecisionResult.BLOCK)
    d2 = engine.check_monotonic_constraint(req)
    assert d2.decision == DecisionResult.BLOCK

    # Attempting to register ALLOW cannot downgrade the BLOCK floor
    engine.register_decision(req, DecisionResult.ALLOW)
    d3 = engine.check_monotonic_constraint(req)
    assert d3.decision == DecisionResult.BLOCK


# ── 5. Safe SQL Query Agent & Ingestion Protection Tests ───────────────────────

def test_parameterized_sql_query(tmp_path):
    db_path = tmp_path / "test_emp.db"
    res = run_sqlite_query(
        query="SELECT name, role FROM employees WHERE department = ? ORDER BY name ASC;",
        params=["Engineering"],
        db_path=db_path,
    )
    assert res["success"] is True
    assert res["count"] > 0
    # Alice Johnson is VP of Engineering
    assert any("Alice Johnson" in str(row) for row in res["rows"])


def test_sql_blocks_multi_statement_ingestion(tmp_path):
    db_path = tmp_path / "test_emp.db"
    # Ingestion attack attempting stacked queries
    attack_query = "SELECT * FROM employees; DROP TABLE departments;"
    res = run_sqlite_query(query=attack_query, db_path=db_path)
    assert res["success"] is False
    assert "multi-statement" in res["error"].lower()


def test_sql_blocks_dangerous_ddl(tmp_path):
    db_path = tmp_path / "test_emp.db"
    ddl_query = "DROP TABLE employees;"
    res = run_sqlite_query(query=ddl_query, db_path=db_path)
    assert res["success"] is False
    assert "dangerous" in res["error"].lower() or "blocked" in res["error"].lower()


def test_sql_read_only_mode(tmp_path):
    db_path = tmp_path / "test_emp.db"
    mutate_query = "UPDATE employees SET salary = 999999 WHERE id = 101;"
    res = run_sqlite_query(query=mutate_query, db_path=db_path, read_only=True)
    assert res["success"] is False
    assert "read-only mode" in res["error"].lower()

