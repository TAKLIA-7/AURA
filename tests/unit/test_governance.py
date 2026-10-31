"""Unit tests for AURA organizational governance, roles, versions, and protected resources."""
import pytest
from pathlib import Path
from aura.governance.manager import GovernanceManager
from aura.governance.models import OrgPolicy, PolicyRuleDef
from aura.models import ActionRequest, DecisionResult
from aura.policies import PolicyEngine


@pytest.fixture
def governance_mgr(tmp_path: Path) -> GovernanceManager:
    db_file = tmp_path / "test_gov.db"
    return GovernanceManager(db_file)


def test_seed_defaults(governance_mgr: GovernanceManager):
    org = governance_mgr.get_organization("default-org")
    assert org is not None
    assert org["name"] == "AURA Enterprise Global"

    policies = governance_mgr.get_active_policies("default-org")
    assert len(policies) >= 1
    assert policies[0].version == 1


def test_protected_resource_evaluation(governance_mgr: GovernanceManager):
    # Confidential salary query by analyst requires approval
    req = ActionRequest(
        tool="sqlite.query",
        operation="query",
        target="sqlite:employees",
        arguments={"query": "SELECT name, salary FROM employees;"},
        org_id="default-org",
        role="analyst",
    )
    res = governance_mgr.evaluate_request(req)
    assert res is not None
    dec, reason, rule_id = res
    assert dec == DecisionResult.APPROVAL_REQUIRED
    assert "protected resource" in reason.lower()

    # Same query by admin is allowed by protected resource rule
    req_admin = ActionRequest(
        tool="sqlite.query",
        operation="query",
        target="sqlite:employees",
        arguments={"query": "SELECT name, salary FROM employees;"},
        org_id="default-org",
        role="admin",
    )
    res_admin = governance_mgr.evaluate_request(req_admin)
    assert res_admin is None  # Admin passes through protected resource check


def test_policy_versioning(governance_mgr: GovernanceManager):
    # Add v2 of base policy
    v2_policy = OrgPolicy(
        org_id="default-org",
        name="Enterprise Base Governance Policy",
        version=2,
        description="Updated strict policy",
        rules=[
            PolicyRuleDef(
                rule_id="RULE-V2-001",
                action_pattern="shell.*",
                effect=DecisionResult.BLOCK,
                reason="Shell execution strictly prohibited in v2",
            )
        ],
    )
    governance_mgr.add_policy_version(v2_policy)

    active = governance_mgr.get_active_policies("default-org")
    assert len(active) == 1
    assert active[0].version == 2

    # Verify rule in v2 triggers
    req = ActionRequest(tool="shell.execute", arguments={"command": "dir"})
    res = governance_mgr.evaluate_request(req)
    assert res is not None
    assert res[0] == DecisionResult.BLOCK
    assert "prohibited in v2" in res[1]


def test_policy_engine_integration(tmp_path: Path, governance_mgr: GovernanceManager):
    engine = PolicyEngine(tmp_path, governance_manager=governance_mgr)
    
    # Mutating sqlite query by non-admin triggers approval in pre_assessment_check
    req = ActionRequest(
        tool="sqlite.execute",
        operation="mutate",
        arguments={"query": "UPDATE employees SET salary = 1000;"},
        org_id="default-org",
        role="analyst",
    )
    decision = engine.pre_assessment_check(req)
    assert decision is not None
    assert decision.decision == DecisionResult.APPROVAL_REQUIRED
    assert "[Org Policy]" in decision.reason
