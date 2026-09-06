"""Deterministic exact -> rule -> fuzzy reconciliation with evidence."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import date
from pathlib import Path

from rapidfuzz.fuzz import token_sort_ratio

from backend.app.ingest import ingest_pair
from backend.app.policies import Policy, load_policy

Transaction = Mapping[str, object]
MatchPolicy = Policy  # Backwards-compatible public name for early consumers.


def _text(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold()).strip()


def _similarity(left: object, right: object) -> float:
    left_text, right_text = _text(left), _text(right)
    if not left_text or not right_text:
        return 0.0
    return round(token_sort_ratio(left_text, right_text) / 100, 4)


def _date_distance(left: Transaction, right: Transaction) -> int:
    return abs(
        (
            date.fromisoformat(str(left["date"]))
            - date.fromisoformat(str(right["date"]))
        ).days
    )


def _amount_distance(left: Transaction, right: Transaction) -> float:
    return round(abs(float(left["amount"]) - float(right["amount"])), 2)


def _same_currency(left: Transaction, right: Transaction) -> bool:
    return str(left.get("currency", "USD")) == str(right.get("currency", "USD"))


def _same_reference(left: Transaction, right: Transaction) -> bool:
    reference = _text(left.get("reference"))
    return bool(reference) and reference == _text(right.get("reference"))


def _field_scores(
    bank: Transaction, gl: Transaction, policy: Policy
) -> dict[str, float]:
    amount_delta = _amount_distance(bank, gl)
    amount_scale = max(abs(float(bank["amount"])), 1.0)
    amount_score = max(0.0, 1.0 - amount_delta / amount_scale)
    date_score = max(0.0, 1.0 - _date_distance(bank, gl) / 7)
    return {
        "amount": round(amount_score, 4),
        "date_proximity": round(date_score, 4),
        "counterparty": _similarity(bank.get("counterparty"), gl.get("counterparty")),
        "reference": _similarity(bank.get("reference"), gl.get("reference")),
    }


def _fuzzy_confidence(scores: Mapping[str, float]) -> float:
    # Counterparty is the primary fuzzy signal (60%). Exact amount and nearby
    # date are safety anchors (20% and 10%); reference similarity is secondary
    # (10%). The weights sum to one, so confidence is always in [0, 1].
    confidence = (
        scores["counterparty"] * 0.60
        + scores["amount"] * 0.20
        + scores["date_proximity"] * 0.10
        + scores["reference"] * 0.10
    )
    return round(min(1.0, max(0.0, confidence)), 4)


def _source_rows(bank: Transaction, gl: Transaction) -> dict[str, object]:
    return {"bank": bank.get("raw", {}), "gl": gl.get("raw", {})}


def _matched_decision(
    bank: Transaction,
    gl: Transaction,
    policy: Policy,
    *,
    method: str,
    confidence: float,
) -> dict[str, object]:
    scores = _field_scores(bank, gl, policy)
    reasons = (
        [
            "reference exact",
            "amount exact",
            f"date gap {_date_distance(bank, gl)}d is within exact-match limit 1d",
        ]
        if method == "exact"
        else [
            f"counterparty token similarity {scores['counterparty']:.2f}",
            (
                f"fuzzy composite {confidence:.2f} meets policy v{policy.version} "
                f"threshold {policy.fuzzy_threshold:.2f}"
            ),
        ]
    )
    counterfactual = (
        "would not auto-match if reference or amount differed, or date gap exceeded 1d"
        if method == "exact"
        else f"would not auto-match below policy v{policy.version} fuzzy threshold "
        f"{policy.fuzzy_threshold:.2f}"
    )
    return {
        "pair": [str(bank["id"]), str(gl["id"])],
        "status": "matched",
        "method": method,
        "confidence": confidence,
        "evidence": {
            "field_scores": scores,
            "reasons": reasons,
            "counterfactual": counterfactual,
            "source_rows": _source_rows(bank, gl),
        },
    }


def _exception(
    exception_id: str,
    kind: str,
    items: list[str],
    confidence: float,
    suggestion: str,
    evidence: dict[str, object],
) -> dict[str, object]:
    return {
        "id": exception_id,
        "kind": kind,
        "primary_kind": kind,
        "secondary_tags": [],
        "items": items,
        "disposition": "needs_review",
        "suggestion": suggestion,
        "confidence": round(min(1.0, max(0.0, confidence)), 4),
        "evidence": evidence,
    }


def _pair_evidence(
    bank: Transaction,
    gl: Transaction,
    policy: Policy,
    *,
    reasons: list[str],
    counterfactual: str,
) -> dict[str, object]:
    return {
        "field_scores": _field_scores(bank, gl, policy),
        "reasons": reasons,
        "counterfactual": counterfactual,
        "source_rows": _source_rows(bank, gl),
    }


def match_transactions(
    bank_transactions: Sequence[Transaction],
    gl_transactions: Sequence[Transaction],
    policy: Policy | None = None,
) -> list[dict[str, object]]:
    """Return schema-valid MatchDecision and Exception records.

    Matching is one-to-one and deterministic. Exceptions are classified here
    only when a rule has direct transactional evidence; no probabilistic or LLM
    disposition can auto-resolve them.
    """

    active_policy = policy or load_policy()
    remaining_bank = {
        str(item["id"]): item
        for item in sorted(bank_transactions, key=lambda item: str(item["id"]))
    }
    remaining_gl = {
        str(item["id"]): item
        for item in sorted(gl_transactions, key=lambda item: str(item["id"]))
    }
    records: list[dict[str, object]] = []
    exception_number = 0

    def next_exception_id() -> str:
        nonlocal exception_number
        exception_number += 1
        return f"EX-{exception_number:04d}"

    # Stage 1 — exact. Duplicate ambiguity is detected before choosing a GL,
    # preventing a repeated booking from being hidden by a greedy exact match.
    for bank_id, bank in list(remaining_bank.items()):
        candidates = [
            gl
            for gl in remaining_gl.values()
            if _same_currency(bank, gl)
            and _same_reference(bank, gl)
            and _amount_distance(bank, gl) == 0
            and _date_distance(bank, gl) <= 1
        ]
        if len(candidates) >= 2:
            candidates.sort(key=lambda item: str(item["id"]))
            candidate_ids = [str(item["id"]) for item in candidates]
            scores = _field_scores(bank, candidates[0], active_policy)
            records.append(
                _exception(
                    next_exception_id(),
                    "DUPLICATE",
                    [bank_id, *candidate_ids],
                    1.0,
                    "Review the repeated GL bookings and retain only the valid entry.",
                    {
                        "field_scores": scores,
                        "reasons": [
                            f"multiple equally valid GL candidates ({len(candidates)})",
                            f"candidate IDs: {', '.join(candidate_ids)}",
                        ],
                        "counterfactual": (
                            "not auto-resolved because multiple equally valid GL candidates "
                            "create an ambiguity requiring controller review"
                        ),
                        "source_rows": {"bank": bank.get("raw", {})},
                        "candidate_rows": [
                            {
                                "id": str(candidate["id"]),
                                "source": "gl",
                                "raw": candidate.get("raw", {}),
                            }
                            for candidate in candidates
                        ],
                    },
                )
            )
            del remaining_bank[bank_id]
            for candidate_id in candidate_ids:
                del remaining_gl[candidate_id]
        elif len(candidates) == 1:
            gl = candidates[0]
            records.append(
                _matched_decision(
                    bank, gl, active_policy, method="exact", confidence=1.0
                )
            )
            del remaining_bank[bank_id]
            del remaining_gl[str(gl["id"])]

    # Stage 2 — deterministic reference rules for known exception types.
    for bank_id, bank in list(remaining_bank.items()):
        same_reference = [
            gl
            for gl in remaining_gl.values()
            if _same_currency(bank, gl) and _same_reference(bank, gl)
        ]
        if not same_reference:
            continue
        same_reference.sort(
            key=lambda gl: (
                _amount_distance(bank, gl),
                _date_distance(bank, gl),
                str(gl["id"]),
            )
        )
        gl = same_reference[0]
        amount_delta = _amount_distance(bank, gl)
        date_gap = _date_distance(bank, gl)
        if amount_delta > 0:
            records.append(
                _exception(
                    next_exception_id(),
                    "AMOUNT_MISMATCH",
                    [bank_id, str(gl["id"])],
                    _field_scores(bank, gl, active_policy)["amount"],
                    f"Review the ${amount_delta:.2f} difference before posting an adjustment.",
                    _pair_evidence(
                        bank,
                        gl,
                        active_policy,
                        reasons=[
                            "reference exact",
                            f"amount differs by ${amount_delta:.2f}",
                        ],
                        counterfactual=(
                            f"not auto-resolved because amount delta ${amount_delta:.2f} "
                            f"exceeds policy tolerance ${active_policy.amount_tolerance:.2f}"
                        ),
                    ),
                )
            )
        elif date_gap > active_policy.date_grace_days:
            records.append(
                _exception(
                    next_exception_id(),
                    "TIMING_DIFF",
                    [bank_id, str(gl["id"])],
                    _field_scores(bank, gl, active_policy)["date_proximity"],
                    "Review the posting period and approve the timing difference if expected.",
                    _pair_evidence(
                        bank,
                        gl,
                        active_policy,
                        reasons=[
                            "reference exact",
                            "amount exact",
                            f"dates are {date_gap} days apart",
                        ],
                        counterfactual=(
                            f"not auto-resolved because date gap {date_gap}d exceeds policy "
                            f"grace {active_policy.date_grace_days}d"
                        ),
                    ),
                )
            )
        else:
            continue
        del remaining_bank[bank_id]
        del remaining_gl[str(gl["id"])]

    # Stage 3 — fuzzy counterparty matching. Only amount/date-safe candidates
    # are considered; weak text similarity is escalated instead of auto-closed.
    fuzzy_candidates: list[tuple[float, str, str, Transaction, Transaction]] = []
    for bank_id, bank in remaining_bank.items():
        for gl_id, gl in remaining_gl.items():
            if not _same_currency(bank, gl):
                continue
            if _amount_distance(bank, gl) > active_policy.amount_tolerance:
                continue
            if _date_distance(bank, gl) > active_policy.date_grace_days:
                continue
            scores = _field_scores(bank, gl, active_policy)
            fuzzy_candidates.append(
                (_fuzzy_confidence(scores), bank_id, gl_id, bank, gl)
            )

    for confidence, bank_id, gl_id, bank, gl in sorted(
        fuzzy_candidates, key=lambda item: (-item[0], item[1], item[2])
    ):
        if bank_id not in remaining_bank or gl_id not in remaining_gl:
            continue
        scores = _field_scores(bank, gl, active_policy)
        if confidence >= active_policy.fuzzy_threshold:
            records.append(
                _matched_decision(
                    bank,
                    gl,
                    active_policy,
                    method="fuzzy",
                    confidence=confidence,
                )
            )
        else:
            records.append(
                _exception(
                    next_exception_id(),
                    "COUNTERPARTY_MISMATCH",
                    [bank_id, gl_id],
                    confidence,
                    "Confirm the counterparty identity before approving this pair.",
                    _pair_evidence(
                        bank,
                        gl,
                        active_policy,
                        reasons=[
                            "amount and date satisfy policy safety gates",
                            f"counterparty token similarity {scores['counterparty']:.2f}",
                            f"fuzzy composite {confidence:.2f} is below threshold",
                        ],
                        counterfactual=(
                            f"not auto-resolved because fuzzy composite {confidence:.2f} "
                            f"is below policy v{active_policy.version} threshold "
                            f"{active_policy.fuzzy_threshold:.2f}"
                        ),
                    ),
                )
            )
        del remaining_bank[bank_id]
        del remaining_gl[gl_id]

    for transaction_id, transaction in sorted(remaining_bank.items()):
        records.append(
            _exception(
                next_exception_id(),
                "MISSING_ENTRY",
                [transaction_id],
                1.0,
                "Draft the missing GL entry or identify the absent counterpart.",
                {
                    "field_scores": {
                        "amount": 0.0,
                        "date_proximity": 0.0,
                        "counterparty": 0.0,
                        "reference": 0.0,
                    },
                    "reasons": [
                        "no unused GL candidate satisfies amount and date safety gates"
                    ],
                    "counterfactual": "not auto-resolved because no GL counterpart exists",
                    "source_rows": {"bank": transaction.get("raw", {})},
                },
            )
        )
    for transaction_id, transaction in sorted(remaining_gl.items()):
        records.append(
            _exception(
                next_exception_id(),
                "MISSING_ENTRY",
                [transaction_id],
                1.0,
                "Identify the missing bank-side transaction or reverse the GL entry.",
                {
                    "field_scores": {
                        "amount": 0.0,
                        "date_proximity": 0.0,
                        "counterparty": 0.0,
                        "reference": 0.0,
                    },
                    "reasons": [
                        "no unused bank candidate satisfies amount and date safety gates"
                    ],
                    "counterfactual": "not auto-resolved because no bank counterpart exists",
                    "source_rows": {"gl": transaction.get("raw", {})},
                },
            )
        )

    return records


def _summary(
    records: Sequence[Mapping[str, object]],
) -> tuple[Counter[str], Counter[str]]:
    matched = Counter(
        str(record["method"]) for record in records if record.get("status") == "matched"
    )
    exceptions = Counter(str(record["kind"]) for record in records if "kind" in record)
    return matched, exceptions


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run deterministic bank-to-GL matching"
    )
    parser.add_argument("--bank", type=Path, required=True)
    parser.add_argument("--gl", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--policy", type=Path, default=None)
    args = parser.parse_args(argv)

    bank, gl = ingest_pair(args.bank, args.gl)
    policy = load_policy(args.policy) if args.policy else load_policy()
    records = match_transactions(bank, gl, policy)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")

    matched, exceptions = _summary(records)
    print("Matched by method:")
    for method in ("exact", "rule", "fuzzy", "llm"):
        print(f"  {method}: {matched[method]}")
    print("Exceptions by kind:")
    for kind in (
        "TIMING_DIFF",
        "DUPLICATE",
        "MISSING_ENTRY",
        "AMOUNT_MISMATCH",
        "COUNTERPARTY_MISMATCH",
        "UNKNOWN",
    ):
        print(f"  {kind}: {exceptions[kind]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
