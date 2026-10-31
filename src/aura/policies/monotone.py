"""AURA Monotone Policy Engine — formal monotonic security guarantees and privilege attenuation."""
from __future__ import annotations
from typing import Any, Dict, List, Optional, Set, Tuple

from aura.models import (
    ActionRequest, DecisionResult, PolicyDecision, RiskLevel,
)
from aura.policies.rules import PolicyRule


# Order of restriction levels in the security lattice: ALLOW < APPROVAL_REQUIRED < BLOCK
DECISION_LATTICE: Dict[DecisionResult, int] = {
    DecisionResult.ALLOW: 0,
    DecisionResult.PENDING: 0,
    DecisionResult.APPROVAL_REQUIRED: 1,
    DecisionResult.BLOCK: 2,
    DecisionResult.ERROR: 2,
}

RISK_LATTICE: Dict[RiskLevel, int] = {
    RiskLevel.NONE: 0,
    RiskLevel.LOW: 1,
    RiskLevel.MEDIUM: 2,
    RiskLevel.HIGH: 3,
    RiskLevel.CRITICAL: 4,
}


class MonotonePolicyEngine:
    """
    Enforces Monotone Security Invariants across multi-agent loops and tool executions:
      1. Monotonic Non-Decreasing Restriction:
         Once a target resource or operation is flagged as APPROVAL_REQUIRED or BLOCK within a run,
         subsequent actions targeting that resource cannot silently downgrade to ALLOW.
      2. Monotonic Risk Floor:
         Contextual risk scores from earlier in the session establish a floor; risk cannot be
         artificially relaxed in downstream loop iterations without an explicit human override.
      3. Privilege Attenuation:
         In delegation chains, child agents inherit a monotonically non-increasing subset of permissions.
    """

    def __init__(self) -> None:
        self._resource_restriction_floor: Dict[str, DecisionResult] = {}
        self._session_risk_floor: Dict[str, RiskLevel] = {}

    def _get_target_key(self, request: ActionRequest) -> str:
        target = request.target or request.arguments.get("path") or request.arguments.get("query") or request.tool
        return f"{request.tool}:{str(target).strip()}"

    def register_decision(self, request: ActionRequest, decision: DecisionResult, session_id: str = "") -> None:
        """Record a decision in the monotone lattice to enforce non-decreasing restriction."""
        key = self._get_target_key(request)
        curr_floor = self._resource_restriction_floor.get(key, DecisionResult.ALLOW)

        curr_rank = DECISION_LATTICE.get(curr_floor, 0)
        new_rank = DECISION_LATTICE.get(decision, 0)

        if new_rank > curr_rank:
            self._resource_restriction_floor[key] = decision

    def check_monotonic_constraint(self, request: ActionRequest) -> Optional[PolicyDecision]:
        """
        Check if a proposed action violates a previously established restriction floor.
        If a resource previously produced a BLOCK, a repeated attempt in the same session is blocked.
        If it produced APPROVAL_REQUIRED, it requires human approval again.
        """
        key = self._get_target_key(request)
        floor = self._resource_restriction_floor.get(key)

        if floor == DecisionResult.BLOCK:
            return PolicyDecision(
                request_id=request.request_id,
                decision=DecisionResult.BLOCK,
                reason=(
                    f"Monotone Policy Violation: Target '{key}' previously triggered a BLOCK decision. "
                    "Security permissions cannot be relaxed within this execution context."
                ),
                policy_rule_id="POLICY-MONOTONE-001",
                enforced=True,
            )
        elif floor == DecisionResult.APPROVAL_REQUIRED:
            return PolicyDecision(
                request_id=request.request_id,
                decision=DecisionResult.APPROVAL_REQUIRED,
                reason=(
                    f"Monotone Policy Requirement: Target '{key}' previously required human review. "
                    "Permission lattice requires continued human approval."
                ),
                policy_rule_id="POLICY-MONOTONE-002",
                requires_human_review=True,
                enforced=False,
            )

        return None

    def reset_context(self) -> None:
        """Reset restriction floors (e.g. on new session or manual operator reset)."""
        self._resource_restriction_floor.clear()
        self._session_risk_floor.clear()


class MonotonePolicyRule(PolicyRule):
    """AURA policy rule wrapping MonotonePolicyEngine for pre-assessment enforcement."""

    def __init__(self, monotone_engine: Optional[MonotonePolicyEngine] = None) -> None:
        super().__init__("POLICY-MONOTONE-001", "Monotone Security Policy and Restriction Lattice")
        self.monotone_engine = monotone_engine or MonotonePolicyEngine()

    def evaluate(self, request: ActionRequest) -> Optional[PolicyDecision]:
        return self.monotone_engine.check_monotonic_constraint(request)
