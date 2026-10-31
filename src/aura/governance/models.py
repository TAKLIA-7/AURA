"""AURA Organizational Governance typed data models."""
from __future__ import annotations
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from aura.models import DecisionResult, RiskLevel


class OrgRole(BaseModel):
    name: str  # e.g., "admin", "auditor", "analyst", "operator"
    org_id: str = "default-org"
    description: str = ""
    permissions: List[str] = Field(default_factory=list)  # e.g. ["query:read", "query:mutate", "fs:read"]


class ProtectedResource(BaseModel):
    resource_id: str = Field(default_factory=lambda: f"res_{uuid.uuid4().hex[:8]}")
    org_id: str = "default-org"
    name: str  # e.g., "table:employees.salary", "path:credentials/*"
    resource_type: str = "database_column"  # database_table, database_column, filesystem, shell
    classification: str = "confidential"
    requires_approval: bool = True
    allowed_roles: List[str] = Field(default_factory=lambda: ["admin"])


class PolicyRuleDef(BaseModel):
    rule_id: str = Field(default_factory=lambda: f"rule_{uuid.uuid4().hex[:6]}")
    action_pattern: str  # e.g. "sqlite.*", "filesystem.write", "*"
    effect: DecisionResult = DecisionResult.ALLOW
    conditions: Dict[str, Any] = Field(default_factory=dict)  # e.g. {"max_rows": 1000, "operation": "mutate"}
    reason: str = ""
    requires_human_approval: bool = False
    allowed_roles: List[str] = Field(default_factory=list)


class OrgPolicy(BaseModel):
    policy_id: str = Field(default_factory=lambda: f"pol_{uuid.uuid4().hex[:8]}")
    org_id: str = "default-org"
    name: str
    version: int = 1
    description: str = ""
    rules: List[PolicyRuleDef] = Field(default_factory=list)
    protected_resources: List[str] = Field(default_factory=list)
    required_approval_roles: List[str] = Field(default_factory=lambda: ["admin", "compliance_officer"])
    is_active: bool = True
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
