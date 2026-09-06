"""Triage and review trust gates mirroring web/src/trustGate.ts."""

from __future__ import annotations

import re
from typing import Any

AMOUNT_KEYS = {
    "amount",
    "signed_amount",
    "debit",
    "credit",
    "transaction_amount",
    "net_amount",
}

DEFAULT_REVIEW_RULES = [
    {
        "policy_id": "SHORT-PAY",
        "applicable_kinds": ["AMOUNT_MISMATCH"],
        "amount_cap": 0.50,
        "min_confidence": 0.95,
        "allow_bulk": True,
    },
    {
        "policy_id": "MATCH-01",
        "applicable_kinds": ["COUNTERPARTY_MISMATCH"],
        "amount_cap": 5000.0,
        "min_confidence": 0.95,
        "allow_bulk": True,
    },
    {
        "policy_id": "BANK-FEE",
        "applicable_kinds": ["MISSING_ENTRY"],
        "amount_cap": 100.0,
        "min_confidence": 0.98,
        "allow_bulk": True,
    },
]


def parse_amount(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip().replace("$", "").replace(",", "").replace(" ", "")
    if normalized.startswith("(") and normalized.endswith(")"):
        normalized = "-" + normalized[1:-1]
    try:
        return float(normalized)
    except ValueError:
        return None


def evidence_amount(item: dict[str, Any]) -> float | None:
    amounts: list[float] = []
    evidence = item.get("evidence", {})
    source_rows = evidence.get("source_rows", {})
    for row in source_rows.values():
        if not isinstance(row, dict):
            continue
        for key, value in row.items():
            if key.lower() in AMOUNT_KEYS:
                parsed = parse_amount(value)
                if parsed is not None:
                    amounts.append(abs(parsed))
    return max(amounts) if amounts else None


def bulk_approval_gate(
    item: dict[str, Any], rules: list[dict[str, Any]]
) -> dict[str, Any]:
    if item.get("disposition") != "needs_review":
        return {"eligible": False, "reason": "Item is not awaiting review."}

    primary_kind = item.get("primary_kind") or item.get("kind")
    if primary_kind == "DUPLICATE":
        return {
            "eligible": False,
            "reason": "Duplicates always require individual controller approval.",
        }

    amount = evidence_amount(item)
    if amount is None:
        return {
            "eligible": False,
            "reason": "Evidence does not contain a traceable amount.",
        }

    rule = next(
        (
            r
            for r in rules
            if r.get("allow_bulk") and primary_kind in r.get("applicable_kinds", [])
        ),
        None,
    )
    if not rule:
        return {
            "eligible": False,
            "reason": f"No bulk-review policy covers {primary_kind}.",
        }

    confidence = float(item.get("confidence", 0.0))
    min_confidence = float(rule.get("min_confidence", 1.0))
    if confidence < min_confidence:
        return {
            "eligible": False,
            "reason": f"Confidence is below {round(min_confidence * 100)}%.",
        }

    amount_cap = float(rule.get("amount_cap", 0.0))
    if abs(amount) > amount_cap:
        return {
            "eligible": False,
            "reason": f"Amount exceeds {rule.get('policy_id')}'s {amount_cap:.2f} cap.",
        }

    return {
        "eligible": True,
        "rule": rule,
        "amount": abs(amount),
    }
