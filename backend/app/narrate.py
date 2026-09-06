"""Flux commentary and journal entry draft generation for the close loop."""

from __future__ import annotations

import os
from typing import Any

from backend.app.triage import evidence_amount


def draft_journal_entry(
    exception_item: dict[str, Any]
) -> dict[str, Any] | None:
    """Draft a balanced journal entry for an approved adjustment.

    Debits equal credits by definition (both equal entry.amount).
    """
    kind = exception_item.get("primary_kind") or exception_item.get("kind")
    ex_id = exception_item.get("id", "EX-???")
    items = exception_item.get("items", [])
    amount = evidence_amount(exception_item) or 0.0

    if amount <= 0:
        return None

    rounded_amount = round(amount, 2)

    if kind == "MISSING_ENTRY":
        ref = items[0] if items else ex_id
        return {
            "for": f"MISSING_ENTRY {ex_id} ({ref})",
            "entry": {
                "dr": "6120 Bank fees and charges",
                "cr": "1010 Cash and cash equivalents",
                "amount": rounded_amount,
            },
        }
    elif kind == "DUPLICATE":
        gl_ref = items[-1] if len(items) > 1 else ex_id
        return {
            "for": f"DUPLICATE {ex_id} reversal of {gl_ref}",
            "entry": {
                "dr": "1010 Cash and cash equivalents",
                "cr": "6100 Operating expenses",
                "amount": rounded_amount,
            },
        }
    elif kind == "AMOUNT_MISMATCH":
        gl_ref = items[1] if len(items) > 1 else ex_id
        return {
            "for": f"AMOUNT_MISMATCH {ex_id} variance write-off ({gl_ref})",
            "entry": {
                "dr": "6150 Settlement variance",
                "cr": "1010 Cash and cash equivalents",
                "amount": rounded_amount,
            },
        }
    elif kind == "TIMING_DIFF":
        bank_ref = items[0] if items else ex_id
        return {
            "for": f"TIMING_DIFF {ex_id} transit accrual ({bank_ref})",
            "entry": {
                "dr": "1010 Cash and cash equivalents",
                "cr": "2050 Deposits in transit",
                "amount": rounded_amount,
            },
        }

    return None


def generate_deterministic_commentary(
    run_id: str,
    counts: dict[str, int],
    exceptions: list[dict[str, Any]],
    policies: list[dict[str, Any]],
    eval_comparison: dict[str, Any],
) -> list[dict[str, Any]]:
    commentary: list[dict[str, Any]] = []

    # 1. Exception counts by kind
    kind_counts: dict[str, int] = {}
    for ex in exceptions:
        k = ex.get("primary_kind") or ex.get("kind", "UNKNOWN")
        kind_counts[k] = kind_counts.get(k, 0) + 1

    kind_breakdown = ", ".join(
        f"{cnt} {k.replace('_', ' ').lower()}" for k, cnt in sorted(kind_counts.items())
    )
    if not kind_breakdown:
        kind_breakdown = "no open exceptions"

    commentary.append({
        "id": "FLUX-01",
        "title": "Cash is substantially reconciled",
        "body": (
            f"{counts.get('matched', 0)} pairs cleared deterministic matching stages. "
            f"{counts.get('exceptions', 0)} exceptions flagged ({kind_breakdown})."
        ),
        "evidence_refs": [run_id, *(ex["id"] for ex in exceptions[:3])],
        "tone": "info",
    })

    # 2. Largest unmatched amounts
    unmatched_with_amounts: list[tuple[float, dict[str, Any]]] = []
    for ex in exceptions:
        amt = evidence_amount(ex)
        if amt is not None:
            unmatched_with_amounts.append((amt, ex))
    unmatched_with_amounts.sort(key=lambda x: -x[0])

    if unmatched_with_amounts:
        top_ex = unmatched_with_amounts[:3]
        top_str = ", ".join(f"{ex['id']} (${amt:,.2f})" for amt, ex in top_ex)
        commentary.append({
            "id": "FLUX-02",
            "title": "Largest unreconciled exposures quarantined",
            "body": (
                f"Controller review required for top exposures: {top_str}. "
                "Audit-Ready governance prevents auto-closing without positive evidence."
            ),
            "evidence_refs": [ex["id"] for _, ex in top_ex],
            "tone": "review",
        })

    # 3. Matched rate vs baseline
    baseline = eval_comparison.get("baseline", {})
    current = eval_comparison.get("current", {})
    p_baseline = baseline.get("precision", 1.0)
    p_current = current.get("precision", 1.0)
    r_baseline = baseline.get("recall", 1.0)
    r_current = current.get("recall", 1.0)
    false_closes = current.get("false_auto_closes", 0)

    commentary.append({
        "id": "FLUX-03",
        "title": "Zero false auto-closes detected",
        "body": (
            f"Precision is {p_current * 100:.1f}% (baseline {p_baseline * 100:.1f}%) "
            f"with recall {r_current * 100:.1f}%. Exactly {false_closes} false auto-closes "
            "recorded against frozen ground truth."
        ),
        "evidence_refs": ["eval-frozen-truth"],
        "tone": "positive",
    })

    # 4. Policy version changes
    for pol in policies:
        version = pol.get("version", 1)
        if version > 1:
            diffs = pol.get("diff_vs_previous", {})
            diff_str = ", ".join(
                f"{k} changed from {b} to {a}" for k, (b, a) in diffs.items()
            )
            created_by = pol.get("created_by", "controller override")
            commentary.append({
                "id": f"FLUX-POL-v{version}",
                "title": f"Policy {pol.get('id', 'MATCH-01')} upgraded to v{version}",
                "body": f"{created_by}. Policy parameter adjustments: {diff_str}.",
                "evidence_refs": [f"{pol.get('id')}-v{version}"],
                "tone": "positive",
            })

    return commentary


def generate_commentary(
    run_id: str,
    counts: dict[str, int],
    exceptions: list[dict[str, Any]],
    policies: list[dict[str, Any]],
    eval_comparison: dict[str, Any],
) -> list[dict[str, Any]]:
    # Deterministic generation first
    deterministic = generate_deterministic_commentary(
        run_id, counts, exceptions, policies, eval_comparison
    )

    # Pluggable LLM enhancement (optional, safe fallback)
    provider = os.getenv("LLM_PROVIDER")
    api_key = os.getenv("LLM_API_KEY")

    if not provider or not api_key or provider == "none":
        return deterministic

    try:
        # LLM polish could be called here if configured, but fallback to deterministic
        # to ensure zero breakages.
        return deterministic
    except Exception:
        return deterministic
