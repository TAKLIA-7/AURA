"""AURA Agent Role-Based Access Control (RBAC) & Principle of Least Privilege."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from aura.models import (
    ActionRequest, AgentIdentity, AgentRole, DecisionResult,
    PolicyDecision, RiskLevel,
)
from aura.policies.rules import PolicyRule


class RoleDefinition:
    def __init__(
        self,
        role: AgentRole,
        description: str,
        allowed_tools: Set[str],
        allowed_operations: Set[str],
        max_risk_level: RiskLevel,
        can_mutate: bool = False,
        can_delegate: bool = False,
    ) -> None:
        self.role = role
        self.description = description
        self.allowed_tools = allowed_tools
        self.allowed_operations = allowed_operations
        self.max_risk_level = max_risk_level
        self.can_mutate = can_mutate
        self.can_delegate = can_delegate


# Default RBAC definitions for specialized agent roles
DEFAULT_ROLE_DEFINITIONS: Dict[AgentRole, RoleDefinition] = {
    AgentRole.ADMIN: RoleDefinition(
        role=AgentRole.ADMIN,
        description="Full access to all registered tools with mutation privileges",
        allowed_tools={
            "filesystem.list", "filesystem.read", "filesystem.write",
            "sqlite.query", "sqlite.execute", "sqlite_query", "sqlite_execute",
            "shell.execute", "diagnostic.ping", "mock.external_action",
        },
        allowed_operations={"list", "read", "write", "query", "mutate", "execute", "ping", "send"},
        max_risk_level=RiskLevel.CRITICAL,
        can_mutate=True,
        can_delegate=True,
    ),
    AgentRole.SUPERVISOR: RoleDefinition(
        role=AgentRole.SUPERVISOR,
        description="Orchestrator/supervisor agent with delegation and read-only inspection",
        allowed_tools={
            "filesystem.list", "filesystem.read",
            "sqlite.query", "sqlite_query",
            "diagnostic.ping",
        },
        allowed_operations={"list", "read", "query", "ping"},
        max_risk_level=RiskLevel.HIGH,
        can_mutate=False,
        can_delegate=True,
    ),
    AgentRole.SQL_AGENT: RoleDefinition(
        role=AgentRole.SQL_AGENT,
        description="Database specialist agent restricted exclusively to SQLite queries",
        allowed_tools={"sqlite.query", "sqlite_query"},
        allowed_operations={"query"},
        max_risk_level=RiskLevel.MEDIUM,
        can_mutate=False,
        can_delegate=False,
    ),
    AgentRole.FS_AGENT: RoleDefinition(
        role=AgentRole.FS_AGENT,
        description="Filesystem specialist agent restricted to reading workspace files",
        allowed_tools={"filesystem.list", "filesystem.read"},
        allowed_operations={"list", "read"},
        max_risk_level=RiskLevel.LOW,
        can_mutate=False,
        can_delegate=False,
    ),
    AgentRole.DIAGNOSTIC_AGENT: RoleDefinition(
        role=AgentRole.DIAGNOSTIC_AGENT,
        description="Health-check diagnostic agent restricted to network pings",
        allowed_tools={"diagnostic.ping"},
        allowed_operations={"ping"},
        max_risk_level=RiskLevel.NONE,
        can_mutate=False,
        can_delegate=False,
    ),
    AgentRole.EXTERNAL_AGENT: RoleDefinition(
        role=AgentRole.EXTERNAL_AGENT,
        description="Integration agent restricted to external mock services",
        allowed_tools={"mock.external_action", "diagnostic.ping"},
        allowed_operations={"send", "ping"},
        max_risk_level=RiskLevel.HIGH,
        can_mutate=False,
        can_delegate=False,
    ),
    AgentRole.GENERAL: RoleDefinition(
        role=AgentRole.GENERAL,
        description="Standard general-purpose agent with default safe toolset",
        allowed_tools={
            "filesystem.list", "filesystem.read",
            "sqlite.query", "sqlite_query",
            "diagnostic.ping",
        },
        allowed_operations={"list", "read", "query", "ping"},
        max_risk_level=RiskLevel.MEDIUM,
        can_mutate=False,
        can_delegate=True,
    ),
    AgentRole.GUEST: RoleDefinition(
        role=AgentRole.GUEST,
        description="Unauthenticated or untrusted guest agent with minimal diagnostic access",
        allowed_tools={"diagnostic.ping"},
        allowed_operations={"ping"},
        max_risk_level=RiskLevel.NONE,
        can_mutate=False,
        can_delegate=False,
    ),
}


class AgentRBACManager:
    """Manages agent registrations, role definitions, permission checks, and delegation attenuation."""

    def __init__(self, role_definitions: Optional[Dict[AgentRole, RoleDefinition]] = None) -> None:
        self.role_definitions = role_definitions or dict(DEFAULT_ROLE_DEFINITIONS)
        self._identities: Dict[str, AgentIdentity] = {}

    def register_agent(self, identity: AgentIdentity) -> None:
        """Register an agent identity with its assigned role and TTL."""
        self._identities[identity.agent_id] = identity

    def get_agent(self, agent_id: str) -> Optional[AgentIdentity]:
        return self._identities.get(agent_id)

    def is_action_allowed(self, request: ActionRequest) -> Tuple[bool, str]:
        """
        Validate whether the requesting agent is permitted to invoke the tool and operation.
        Enforces:
          1. Agent existence and TTL validity.
          2. Tool membership in the role's allowed_tools.
          3. Operation compatibility (read-only vs mutating).
        """
        agent_id = request.agent_id or "default_agent"
        identity = self._identities.get(agent_id)

        # Determine effective role
        role: AgentRole
        if identity:
            role = identity.role
            # Check TTL expiry if configured
            if identity.ttl_seconds is not None:
                elapsed = (datetime.now(timezone.utc) - identity.created_at).total_seconds()
                if elapsed > identity.ttl_seconds:
                    return False, f"Agent token/session for '{agent_id}' has expired (TTL={identity.ttl_seconds}s, elapsed={elapsed:.1f}s)"
        else:
            try:
                role = AgentRole(request.agent_role)
            except ValueError:
                role = AgentRole.GENERAL

        role_def = self.role_definitions.get(role)
        if not role_def:
            return False, f"Unknown agent role '{role}'"

        allowed_tools = identity.allowed_tools if (identity and identity.allowed_tools is not None) else role_def.allowed_tools
        if request.tool not in allowed_tools:
            return False, f"Role '{role.value}' for agent '{agent_id}' is not authorized to use tool '{request.tool}'"

        op = request.operation or "query"
        if op == "mutate" and not role_def.can_mutate:
            return False, f"Role '{role.value}' is restricted to read-only operations; mutating action rejected"

        if identity and identity.read_only and op in ("mutate", "write", "execute"):
            return False, f"Agent '{agent_id}' is explicitly configured as read-only; action '{op}' rejected"

        return True, "Authorized"

    def verify_delegation(
        self,
        parent_role: AgentRole,
        child_role: AgentRole,
        requested_tools: Optional[List[str]] = None,
    ) -> Tuple[bool, str]:
        r"""
        Enforce the Principle of Privilege Attenuation:
        A parent agent cannot delegate permissions greater than what it holds ($Priv(Child) \subseteq Priv(Parent)$).
        """
        parent_def = self.role_definitions.get(parent_role)
        child_def = self.role_definitions.get(child_role)

        if not parent_def:
            return False, f"Parent role '{parent_role.value}' does not exist"
        if not child_def:
            return False, f"Child role '{child_role.value}' does not exist"

        if not parent_def.can_delegate:
            return False, f"Parent role '{parent_role.value}' is not permitted to delegate"

        if child_def.can_mutate and not parent_def.can_mutate:
            return False, f"Privilege attenuation violation: parent '{parent_role.value}' cannot grant mutation privilege to '{child_role.value}'"

        child_tools = set(requested_tools) if requested_tools else child_def.allowed_tools
        excess_tools = child_tools - parent_def.allowed_tools
        if excess_tools:
            return False, (
                f"Privilege attenuation violation: child requested tools {sorted(excess_tools)} "
                f"which parent '{parent_role.value}' does not possess"
            )

        return True, "Delegation valid under monotonic privilege attenuation"


class AgentRBACRule(PolicyRule):
    """Deterministic AURA policy rule enforcing Agent RBAC prior to JEV assessment."""

    def __init__(self, rbac_manager: Optional[AgentRBACManager] = None) -> None:
        super().__init__("POLICY-RBAC-001", "Agent Role-Based Access Control and Principle of Least Privilege")
        self.rbac_manager = rbac_manager or AgentRBACManager()

    def evaluate(self, request: ActionRequest) -> Optional[PolicyDecision]:
        allowed, reason = self.rbac_manager.is_action_allowed(request)
        if not allowed:
            return PolicyDecision(
                request_id=request.request_id,
                decision=DecisionResult.BLOCK,
                reason=f"RBAC Enforcement: {reason}",
                policy_rule_id=self.rule_id,
                enforced=True,
            )
        return None
