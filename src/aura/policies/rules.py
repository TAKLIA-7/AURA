"""AURA base policy rule interface."""
from __future__ import annotations
from typing import Optional
from aura.models import ActionRequest, PolicyDecision


class PolicyRule:
    def __init__(self, rule_id: str, description: str, enabled: bool = True) -> None:
        self.rule_id = rule_id
        self.description = description
        self.enabled = enabled

    def evaluate(self, request: ActionRequest) -> Optional[PolicyDecision]:
        return None
