"""
Data models for ELM-generated role declarations.

A PipelineDeclaration describes how each adversarial agent role should behave
for a specific task — system prompt, model, token budget, and whether it's active.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class RoleDeclaration:
    """Configuration for a single adversarial agent role."""

    role_name: str               # e.g. "adv:planner"
    system_prompt: str           # Task-aware system prompt
    model_assignment: str        # e.g. "anthropic/claude-sonnet-4-5"
    token_budget: int            # Max tokens for this role's response
    activation: bool             # False → skip this role entirely
    execution_order: int         # Lower = earlier in the round pipeline

    def to_dict(self) -> dict:
        return {
            "role_name": self.role_name,
            "system_prompt": self.system_prompt,
            "model_assignment": self.model_assignment,
            "token_budget": self.token_budget,
            "activation": self.activation,
            "execution_order": self.execution_order,
        }

    @classmethod
    def from_dict(cls, data: dict) -> RoleDeclaration:
        return cls(
            role_name=data["role_name"],
            system_prompt=data["system_prompt"],
            model_assignment=data["model_assignment"],
            token_budget=data["token_budget"],
            activation=data["activation"],
            execution_order=data["execution_order"],
        )


@dataclass
class PipelineDeclaration:
    """Full pipeline configuration produced by the ELM (or static fallback)."""

    task_hash: str
    domain: str
    declarations: list[RoleDeclaration]
    generated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    elm_model: str = "static"    # "phi-3-mini-4k-instruct-onnx" or "static"
    cache_key: str = ""

    def get_declaration(self, role_name: str) -> RoleDeclaration | None:
        """Look up declaration for a specific role."""
        return next((d for d in self.declarations if d.role_name == role_name), None)

    def active_round_roles(self) -> list[str]:
        """Return active non-planner roles sorted by execution_order."""
        return [
            d.role_name
            for d in sorted(self.declarations, key=lambda d: d.execution_order)
            if d.activation and d.role_name != "adv:planner"
        ]

    def to_dict(self) -> dict:
        return {
            "task_hash": self.task_hash,
            "domain": self.domain,
            "declarations": [d.to_dict() for d in self.declarations],
            "generated_at": self.generated_at,
            "elm_model": self.elm_model,
            "cache_key": self.cache_key,
        }

    @classmethod
    def from_dict(cls, data: dict) -> PipelineDeclaration:
        return cls(
            task_hash=data["task_hash"],
            domain=data["domain"],
            declarations=[RoleDeclaration.from_dict(d) for d in data["declarations"]],
            generated_at=data.get("generated_at", ""),
            elm_model=data.get("elm_model", "static"),
            cache_key=data.get("cache_key", ""),
        )
