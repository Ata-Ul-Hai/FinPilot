"""Persisted matching policy settings for the deterministic close engine."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_POLICY_PATH = Path(__file__).with_name("policies.json")


class PolicyError(ValueError):
    """Raised when a policy document is invalid."""


@dataclass(frozen=True, slots=True)
class Policy:
    id: str = "MATCH-01"
    version: int = 1
    fuzzy_threshold: float = 0.80
    amount_tolerance: float = 0.0
    date_grace_days: int = 1
    created_by: str = "system default"
    diff_vs_previous: dict[str, list[float]] = field(default_factory=dict)
    eval_impact: dict[str, list[float]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.id:
            raise PolicyError("policy id cannot be empty")
        if self.version < 1:
            raise PolicyError("policy version must be at least 1")
        if not 0 <= self.fuzzy_threshold <= 1:
            raise PolicyError("fuzzy_threshold must be between 0 and 1")
        if self.amount_tolerance < 0:
            raise PolicyError("amount_tolerance cannot be negative")
        if self.date_grace_days < 0:
            raise PolicyError("date_grace_days cannot be negative")

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Policy:
        try:
            rule = value["rule"]
            return cls(
                id=str(value["id"]),
                version=int(value["version"]),
                fuzzy_threshold=float(rule["fuzzy_threshold"]),
                amount_tolerance=float(rule["amount_tolerance"]),
                date_grace_days=int(rule["date_grace_days"]),
                created_by=str(value["created_by"]),
                diff_vs_previous=value.get("diff_vs_previous", {}),
                eval_impact=value.get("eval_impact", {}),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise PolicyError("invalid policy document") from exc

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "version": self.version,
            "rule": {
                "fuzzy_threshold": self.fuzzy_threshold,
                "amount_tolerance": self.amount_tolerance,
                "date_grace_days": self.date_grace_days,
            },
            "created_by": self.created_by,
            "diff_vs_previous": self.diff_vs_previous,
            "eval_impact": self.eval_impact,
        }


def load_policy(path: str | Path = DEFAULT_POLICY_PATH) -> Policy:
    policy_path = Path(path)
    try:
        value = json.loads(policy_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PolicyError(f"unable to load policy from {policy_path}") from exc
    if not isinstance(value, dict):
        raise PolicyError("policy document must be a JSON object")
    return Policy.from_dict(value)


def save_policy(policy: Policy, path: str | Path = DEFAULT_POLICY_PATH) -> None:
    policy_path = Path(path)
    policy_path.parent.mkdir(parents=True, exist_ok=True)
    policy_path.write_text(
        json.dumps(policy.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
