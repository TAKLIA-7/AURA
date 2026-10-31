"""AURA Multi-Agent Swarm Runtime — Coordination, Least Privilege & Attenuation."""
from __future__ import annotations
import asyncio
import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, AsyncGenerator, Callable, Dict, List, Optional, Set, Tuple

from aura.models import (
    ActionRequest, AgentIdentity, AgentRole, AuditEvent, EventLevel, RiskLevel,
)
from aura.policies.rbac import AgentRBACManager

if TYPE_CHECKING:
    from aura.agent import AURAOrchestrator, AgentMessage


@dataclass
class SwarmMember:
    """Definition of an individual agent persona within the AURA multi-agent swarm."""
    agent_id: str
    role: AgentRole
    name: str
    avatar: str
    description: str
    system_prompt: str
    allowed_tools: Set[str]
    read_only: bool = True
    ttl_seconds: Optional[int] = 3600

    def to_identity(self, parent_id: Optional[str] = None) -> AgentIdentity:
        return AgentIdentity(
            agent_id=self.agent_id,
            role=self.role,
            parent_agent_id=parent_id,
            allowed_tools=list(self.allowed_tools),
            read_only=self.read_only,
            ttl_seconds=self.ttl_seconds,
        )


# Standard Specialized Swarm Roster
STANDARD_SWARM_ROSTER: Dict[str, SwarmMember] = {
    "supervisor": SwarmMember(
        agent_id="supervisor",
        role=AgentRole.SUPERVISOR,
        name="Swarm Supervisor",
        avatar="👑",
        description="Coordinates swarm tasks, decomposes complex user inquiries, and delegates subtasks.",
        system_prompt=(
            "You are the Swarm Supervisor Agent. You plan complex objectives, coordinate execution, "
            "delegate SQL inquiries to sql_agent, workspace inquiries to fs_agent, and system checks to security_agent. "
            "Always synthesize specialized findings into a clear, cohesive final response."
        ),
        allowed_tools={"sqlite.query", "sqlite_query", "filesystem.read", "filesystem.list", "diagnostic.ping"},
        read_only=True,
    ),
    "sql_agent": SwarmMember(
        agent_id="sql_agent",
        role=AgentRole.SQL_AGENT,
        name="SQL Data Specialist",
        avatar="💾",
        description="Specialized in parameterized queries and analytical evaluation of SQLite databases.",
        system_prompt=(
            "You are the SQL Database Specialist Agent. You examine tables, count records, "
            "and execute read-only parameterized SQL queries against data/employees.db. "
            "Never attempt schema alteration, table drops, or unparameterized queries."
        ),
        allowed_tools={"sqlite.query", "sqlite_query"},
        read_only=True,
    ),
    "fs_agent": SwarmMember(
        agent_id="fs_agent",
        role=AgentRole.FS_AGENT,
        name="Filesystem Analyst",
        avatar="📁",
        description="Specialized in workspace inspection, safe file reading, and directory enumeration.",
        system_prompt=(
            "You are the Filesystem Specialist Agent. You inspect project files, configs, and logs "
            "within the workspace boundary. Never attempt path traversal or out-of-bounds access."
        ),
        allowed_tools={"filesystem.read", "filesystem.list"},
        read_only=True,
    ),
    "security_agent": SwarmMember(
        agent_id="security_agent",
        role=AgentRole.DIAGNOSTIC_AGENT,
        name="Security & Audit Guardian",
        avatar="🛡️",
        description="Specialized in connectivity diagnostics, telemetry verification, and cryptographic audit checks.",
        system_prompt=(
            "You are the Security Guardian Agent. You evaluate system diagnostic reachability, "
            "verify cryptographic audit hash chains, and report telemetry integrity."
        ),
        allowed_tools={"diagnostic.ping"},
        read_only=True,
    ),
}


class SwarmCoordinator:
    """Orchestrates multi-agent swarm operations with monotonic privilege attenuation."""

    def __init__(
        self,
        orchestrator: AURAOrchestrator,
        roster: Optional[Dict[str, SwarmMember]] = None,
    ) -> None:
        self.orchestrator = orchestrator
        self.roster: Dict[str, SwarmMember] = roster or dict(STANDARD_SWARM_ROSTER)
        self.rbac_manager: AgentRBACManager = orchestrator.rbac_manager
        self._register_roster()

    def _register_roster(self) -> None:
        """Register all swarm members into the RBAC policy manager."""
        for member in self.roster.values():
            self.rbac_manager.register_agent(member.to_identity())

    def get_members(self) -> List[SwarmMember]:
        return list(self.roster.values())

    def get_member(self, agent_id: str) -> Optional[SwarmMember]:
        return self.roster.get(agent_id)

    def verify_delegation(self, from_agent_id: str, to_agent_id: str) -> Tuple[bool, str]:
        """
        Check that delegation complies with Monotonic Privilege Attenuation:
        Priv(Child) ⊆ Priv(Parent)
        """
        parent = self.roster.get(from_agent_id)
        child = self.roster.get(to_agent_id)
        if not parent:
            return False, f"Parent agent '{from_agent_id}' is not in the active swarm roster"
        if not child:
            return False, f"Target agent '{to_agent_id}' is not in the active swarm roster"

        return self.rbac_manager.verify_delegation(
            parent_role=parent.role,
            child_role=child.role,
            requested_tools=list(child.allowed_tools),
        )

    def parse_direct_address(self, prompt: str) -> Tuple[Optional[str], str]:
        """Check if user explicitly addressed a specific agent via @agent_name."""
        clean = prompt.strip()
        for agent_id in self.roster:
            prefix = f"@{agent_id}"
            if clean.lower().startswith(prefix.lower()):
                remaining = clean[len(prefix):].strip()
                if remaining.startswith(":") or remaining.startswith(","):
                    remaining = remaining[1:].strip()
                return agent_id, remaining
        return None, prompt

    def plan_swarm_workflow(self, prompt: str) -> List[Dict[str, Any]]:
        """
        Decompose user request into specialized subtasks.
        Detects database inquiries, file inspections, and security/audit checks.
        """
        p_lower = prompt.lower()
        subtasks: List[Dict[str, Any]] = []

        # 1. SQL subtask
        sql_keywords = ["employee", "department", "salary", "salaries", "sql", "database", "sqlite", "table", "records", "count", "highest paid"]
        if any(kw in p_lower for kw in sql_keywords):
            subtasks.append({
                "agent_id": "sql_agent",
                "role": AgentRole.SQL_AGENT,
                "task": prompt,
                "domain": "Database Analysis",
            })

        # 2. Filesystem subtask
        fs_keywords = ["read file", "list files", "directory", "log", "config", "pyproject", "requirements", ".env", "readme", "cat "]
        if any(kw in p_lower for kw in fs_keywords):
            subtasks.append({
                "agent_id": "fs_agent",
                "role": AgentRole.FS_AGENT,
                "task": prompt,
                "domain": "Filesystem Inspection",
            })

        # 3. Security / Audit subtask
        sec_keywords = ["audit", "hash chain", "ping", "diagnostics", "security", "tamper", "telemetry", "health"]
        if any(kw in p_lower for kw in sec_keywords):
            subtasks.append({
                "agent_id": "security_agent",
                "role": AgentRole.DIAGNOSTIC_AGENT,
                "task": prompt,
                "domain": "Security & Diagnostics",
            })

        # Default fallback: if no specific keywords matched, route to SQL or general
        if not subtasks:
            subtasks.append({
                "agent_id": "sql_agent",
                "role": AgentRole.SQL_AGENT,
                "task": prompt,
                "domain": "General Query",
            })

        return subtasks

    async def execute_swarm(
        self,
        prompt: str,
        conversation_history: Optional[List[Dict]] = None,
    ) -> AsyncGenerator[Any, None]:
        """
        Run the complete multi-agent swarm loop:
        1. Supervisor plans subtasks.
        2. Monotonic delegation checks ensure Priv(Child) ⊆ Priv(Parent).
        3. Specialized agents execute under their own identities through the AURA gateway.
        4. Findings hand off back to Supervisor for final synthesis.
        """
        from aura.agent import AgentMessage

        # Check for direct single agent addressing (@sql_agent ...)
        direct_target, clean_prompt = self.parse_direct_address(prompt)
        if direct_target and direct_target != "supervisor":
            member = self.roster[direct_target]
            yield AgentMessage("agent_text", f"Directing request to [{member.avatar} {member.name}] (Role: {member.role.value})...")
            async for msg in self.orchestrator.run(
                prompt=clean_prompt,
                conversation_history=conversation_history,
                agent_id=member.agent_id,
                agent_role=member.role.value,
            ):
                yield msg
            return

        # Multi-Agent Swarm Workflow
        supervisor = self.roster["supervisor"]
        subtasks = self.plan_swarm_workflow(prompt)

        yield AgentMessage("agent_text", (
            f"👑 [{supervisor.name}] Activated multi-agent swarm coordinator.\n"
            f"  Identified {len(subtasks)} specialized task(s) to execute."
        ))

        findings: List[str] = []

        for idx, step in enumerate(subtasks, start=1):
            target_id = step["agent_id"]
            target_agent = self.roster[target_id]
            subtask_desc = step["task"]

            # 1. Monotonic Privilege Attenuation Verification
            valid, reason = self.verify_delegation(from_agent_id="supervisor", to_agent_id=target_id)
            if not valid:
                yield AgentMessage("action_blocked", {
                    "tool": "swarm.delegate",
                    "reason": f"Privilege attenuation violation: {reason}",
                    "policy_rule_id": "POLICY-RBAC-001",
                })
                continue

            # 2. Emit Delegation Event
            await self.orchestrator._emit(AuditEvent(
                level=EventLevel.INFO,
                event_type="aura.agent.delegation",
                session_id=self.orchestrator.session_id,
                actor={"type": "agent", "agent_id": "supervisor", "role": supervisor.role.value},
                metadata={
                    "target_agent": target_id,
                    "target_role": target_agent.role.value,
                    "domain": step["domain"],
                    "attenuation_verified": True,
                },
            ))

            delegation_content = {
                "from_agent": "supervisor",
                "to_agent": target_id,
                "avatar": target_agent.avatar,
                "agent_name": target_agent.name,
                "task": subtask_desc,
                "domain": step["domain"],
            }
            yield AgentMessage("agent_delegation", delegation_content, metadata=dict(delegation_content))

            # 3. Execute Subtask with Child Agent's Role & Identity
            child_text_accumulator: List[str] = []
            async for child_msg in self.orchestrator.run(
                prompt=subtask_desc,
                conversation_history=conversation_history,
                agent_id=target_agent.agent_id,
                agent_role=target_agent.role.value,
            ):
                if child_msg.kind == "agent_text":
                    child_text_accumulator.append(child_msg.content)
                yield child_msg

            child_summary = "\n".join(child_text_accumulator).strip()
            findings.append(f"[{target_agent.name} Findings]:\n{child_summary or 'Completed subtask execution.'}")

            # 4. Emit Handoff Back to Supervisor
            await self.orchestrator._emit(AuditEvent(
                level=EventLevel.INFO,
                event_type="aura.agent.handoff",
                session_id=self.orchestrator.session_id,
                actor={"type": "agent", "agent_id": target_id, "role": target_agent.role.value},
                metadata={"return_to": "supervisor", "has_findings": bool(child_summary)},
            ))

            handoff_content = {
                "from_agent": target_id,
                "to_agent": "supervisor",
                "avatar": target_agent.avatar,
                "agent_name": target_agent.name,
                "summary": (child_summary[:180] + "...") if len(child_summary) > 180 else child_summary,
            }
            yield AgentMessage("agent_handoff", handoff_content, metadata=dict(handoff_content))

        # 5. Final Supervisor Synthesis
        if len(findings) > 1 or not findings:
            yield AgentMessage("agent_text", (
                f"👑 [{supervisor.name}] Synthesized results from {len(findings)} swarm specialist(s):\n\n" +
                "\n\n".join(findings)
            ))
