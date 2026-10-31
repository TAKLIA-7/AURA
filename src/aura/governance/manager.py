"""AURA Governance Manager — SQLite-backed organizational policy and role enforcement."""
from __future__ import annotations
import fnmatch
import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from aura.models import ActionRequest, DecisionResult
from aura.governance.models import OrgPolicy, OrgRole, PolicyRuleDef, ProtectedResource

DEFAULT_GOVERNANCE_DB = Path("./data/governance.db")


class GovernanceManager:
    """Manages multi-tenant organizations, policy versions, roles, and protected resources."""

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self.db_path = db_path or DEFAULT_GOVERNANCE_DB
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_tables()
        self._seed_defaults()

    def _get_conn(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self.db_path))

    def _init_tables(self) -> None:
        with self._get_conn() as conn:
            c = conn.cursor()
            c.execute("""
            CREATE TABLE IF NOT EXISTS organizations (
                org_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active'
            );
            """)
            c.execute("""
            CREATE TABLE IF NOT EXISTS org_roles (
                org_id TEXT NOT NULL,
                name TEXT NOT NULL,
                description TEXT,
                permissions_json TEXT NOT NULL,
                PRIMARY KEY (org_id, name)
            );
            """)
            c.execute("""
            CREATE TABLE IF NOT EXISTS protected_resources (
                resource_id TEXT PRIMARY KEY,
                org_id TEXT NOT NULL,
                name TEXT NOT NULL,
                resource_type TEXT NOT NULL,
                classification TEXT NOT NULL,
                requires_approval INTEGER NOT NULL,
                allowed_roles_json TEXT NOT NULL
            );
            """)
            c.execute("""
            CREATE TABLE IF NOT EXISTS org_policies (
                policy_id TEXT PRIMARY KEY,
                org_id TEXT NOT NULL,
                name TEXT NOT NULL,
                version INTEGER NOT NULL,
                description TEXT,
                rules_json TEXT NOT NULL,
                protected_resources_json TEXT NOT NULL,
                required_approval_roles_json TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            );
            """)
            conn.commit()

    def _seed_defaults(self) -> None:
        """Seed default organization and baseline policies if empty."""
        with self._get_conn() as conn:
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM organizations WHERE org_id = 'default-org';")
            if c.fetchone()[0] == 0:
                c.execute(
                    "INSERT INTO organizations (org_id, name, created_at, status) VALUES (?, ?, datetime('now'), 'active')",
                    ("default-org", "AURA Enterprise Global"),
                )

                # Seed baseline roles
                roles = [
                    ("default-org", "admin", "System Administrator", json.dumps(["*"])),
                    ("default-org", "auditor", "Compliance & Audit Viewer", json.dumps(["query:read", "audit:view"])),
                    ("default-org", "analyst", "Data Analyst", json.dumps(["query:read", "fs:read", "calc:run"])),
                ]
                c.executemany("INSERT INTO org_roles VALUES (?, ?, ?, ?)", roles)

                # Seed protected resources
                protected = [
                    ("res_salaries", "default-org", "table:employees.salary", "database_column", "confidential", 1, json.dumps(["admin"])),
                    ("res_credentials", "default-org", "path:.*(key|secret|env).*", "filesystem", "restricted", 1, json.dumps(["admin"])),
                ]
                c.executemany("INSERT INTO protected_resources VALUES (?, ?, ?, ?, ?, ?, ?)", protected)

                # Seed initial versioned policy
                default_rules = [
                    {
                        "rule_id": "ORG-RULE-001",
                        "action_pattern": "sqlite.execute",
                        "effect": "approval_required",
                        "conditions": {"operation": "mutate"},
                        "reason": "Organizational governance requires dual review for all data modifications",
                        "requires_human_approval": True,
                        "allowed_roles": ["admin"],
                    },
                    {
                        "rule_id": "ORG-RULE-002",
                        "action_pattern": "filesystem.write",
                        "effect": "approval_required",
                        "conditions": {},
                        "reason": "Filesystem write access requires human oversight per org security policy",
                        "requires_human_approval": True,
                        "allowed_roles": ["admin"],
                    },
                ]
                c.execute(
                    """INSERT INTO org_policies (
                        policy_id, org_id, name, version, description,
                        rules_json, protected_resources_json, required_approval_roles_json,
                        is_active, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))""",
                    (
                        "pol_baseline_v1",
                        "default-org",
                        "Enterprise Base Governance Policy",
                        1,
                        "Baseline policy requiring human verification on mutating actions and sensitive resources.",
                        json.dumps(default_rules),
                        json.dumps(["table:employees.salary", "path:.*(key|secret|env).*"]),
                        json.dumps(["admin"]),
                        1,
                    ),
                )
                conn.commit()

    def get_organization(self, org_id: str) -> Optional[Dict[str, Any]]:
        with self._get_conn() as conn:
            c = conn.cursor()
            c.execute("SELECT org_id, name, created_at, status FROM organizations WHERE org_id = ?", (org_id,))
            row = c.fetchone()
            if not row:
                return None
            return {"org_id": row[0], "name": row[1], "created_at": row[2], "status": row[3]}

    def create_organization(self, org_id: str, name: str) -> Dict[str, Any]:
        with self._get_conn() as conn:
            c = conn.cursor()
            c.execute(
                "INSERT INTO organizations (org_id, name, created_at, status) VALUES (?, ?, datetime('now'), 'active')",
                (org_id, name),
            )
            conn.commit()
        return {"org_id": org_id, "name": name, "status": "active"}

    def add_policy_version(self, policy: OrgPolicy) -> OrgPolicy:
        """Add a new version of a policy, setting older versions to inactive if matching name."""
        with self._get_conn() as conn:
            c = conn.cursor()
            # Set older versions inactive
            c.execute(
                "UPDATE org_policies SET is_active = 0 WHERE org_id = ? AND name = ?",
                (policy.org_id, policy.name),
            )
            c.execute(
                """INSERT INTO org_policies (
                    policy_id, org_id, name, version, description,
                    rules_json, protected_resources_json, required_approval_roles_json,
                    is_active, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))""",
                (
                    policy.policy_id,
                    policy.org_id,
                    policy.name,
                    policy.version,
                    policy.description,
                    json.dumps([r.model_dump() for r in policy.rules]),
                    json.dumps(policy.protected_resources),
                    json.dumps(policy.required_approval_roles),
                    1 if policy.is_active else 0,
                ),
            )
            conn.commit()
        return policy

    def get_active_policies(self, org_id: str) -> List[OrgPolicy]:
        with self._get_conn() as conn:
            c = conn.cursor()
            c.execute(
                """SELECT policy_id, org_id, name, version, description,
                          rules_json, protected_resources_json, required_approval_roles_json,
                          is_active, created_at
                   FROM org_policies WHERE org_id = ? AND is_active = 1""",
                (org_id,),
            )
            rows = c.fetchall()
            policies = []
            for r in rows:
                rules_data = json.loads(r[5])
                rules = [PolicyRuleDef(**rd) for rd in rules_data]
                policies.append(OrgPolicy(
                    policy_id=r[0], org_id=r[1], name=r[2], version=r[3],
                    description=r[4] or "", rules=rules,
                    protected_resources=json.loads(r[6]),
                    required_approval_roles=json.loads(r[7]),
                    is_active=bool(r[8]), created_at=r[9],
                ))
            return policies

    def evaluate_request(
        self,
        request: ActionRequest,
        org_id: Optional[str] = None,
        role: Optional[str] = None,
    ) -> Optional[Tuple[DecisionResult, str, str]]:
        """
        Evaluate an ActionRequest deterministically against active organizational policies.
        Returns (DecisionResult, reason, rule_id) if an org policy triggers; otherwise None.
        """
        target_org = org_id or getattr(request, "org_id", "default-org")
        target_role = role or getattr(request, "role", "analyst")
        active_policies = self.get_active_policies(target_org)

        # Check protected resources
        with self._get_conn() as conn:
            c = conn.cursor()
            c.execute(
                "SELECT name, allowed_roles_json, requires_approval FROM protected_resources WHERE org_id = ?",
                (target_org,),
            )
            for res_name, roles_json, req_app in c.fetchall():
                allowed_roles = json.loads(roles_json)
                query_text = str(request.arguments.get("query", "")).lower()
                target_str = str(request.target or "").lower()
                raw_pattern = res_name.split(":", 1)[-1].lower()

                # Match if full pattern in query/target, or if both table and column parts are present
                pattern_matched = (raw_pattern in query_text or raw_pattern in target_str)
                if not pattern_matched and "." in raw_pattern:
                    parts = raw_pattern.split(".")
                    # e.g. "employees" and "salary" both in query
                    pattern_matched = all(p in query_text for p in parts)

                if pattern_matched:
                    if target_role not in allowed_roles:
                        if req_app:
                            return (
                                DecisionResult.APPROVAL_REQUIRED,
                                f"Access to protected resource '{res_name}' requires approval for role '{target_role}'",
                                "ORG-PROTECTED-RES-001",
                            )
                        else:
                            return (
                                DecisionResult.BLOCK,
                                f"Role '{target_role}' is not authorized to access protected resource '{res_name}'",
                                "ORG-PROTECTED-RES-BLOCK",
                            )

        # Evaluate policy rules
        for policy in active_policies:
            for rule in policy.rules:
                if fnmatch.fnmatch(request.tool, rule.action_pattern):
                    # Check conditions if any
                    if rule.conditions:
                        op = rule.conditions.get("operation")
                        if op and request.operation != op:
                            continue

                    if rule.requires_human_approval:
                        return (
                            DecisionResult.APPROVAL_REQUIRED,
                            rule.reason or f"Policy '{policy.name}' (v{policy.version}) requires approval.",
                            rule.rule_id,
                        )
                    if rule.effect == DecisionResult.BLOCK:
                        return (
                            DecisionResult.BLOCK,
                            rule.reason or f"Blocked by policy '{policy.name}' (v{policy.version}).",
                            rule.rule_id,
                        )

        return None
