"""Deterministic exact -> rule -> fuzzy reconciliation with evidence."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date

from rapidfuzz.fuzz import ratio

Transaction = Mapping[str, object]


@dataclass(frozen=True, slots=True)
class MatchPolicy:
    """The policy inputs that directly control an automatic match."""

    fuzzy_threshold: float = 0.80
    amount_tolerance: float = 0.0
    date_grace_days: int = 0
    candidate_floor: float = 0.45
    version: int = 1

    def __post_init__(self) -> None:
        if not 0 <= self.fuzzy_threshold <= 1:
            raise ValueError("fuzzy_threshold must be between 0 and 1")
        if self.amount_tolerance < 0:
            raise ValueError("amount_tolerance cannot be negative")
        if self.date_grace_days < 0:
            raise ValueError("date_grace_days cannot be negative")


def _text(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold()).strip()


def _date_distance(left: Transaction, right: Transaction) -> int:
    return abs(
        (
            date.fromisoformat(str(left["date"]))
            - date.fromisoformat(str(right["date"]))
        ).days
    )


def _amount_distance(left: Transaction, right: Transaction) -> float:
    return round(abs(float(left["amount"]) - float(right["amount"])), 2)


def _similarity(left: object, right: object) -> float:
    left_text, right_text = _text(left), _text(right)
    if not left_text and not right_text:
        # Missing values are not corroborating evidence. Treating two blanks as
        # a perfect match can turn an otherwise weak candidate into an unsafe
        # auto-match.
        return 0.0
    if not left_text or not right_text:
        return 0.0
    return round(ratio(left_text, right_text) / 100, 4)


def _field_scores(
    bank: Transaction, gl: Transaction, policy: MatchPolicy
) -> dict[str, float]:
    amount_delta = _amount_distance(bank, gl)
    amount_span = max(policy.amount_tolerance, 0.01)
    amount_score = max(0.0, 1.0 - amount_delta / amount_span)
    days = _date_distance(bank, gl)
    date_span = max(policy.date_grace_days, 7)
    date_score = max(0.0, 1.0 - days / date_span)
    return {
        "amount": round(amount_score, 4),
        "date_proximity": round(date_score, 4),
        "counterparty": _similarity(bank.get("counterparty"), gl.get("counterparty")),
        "reference": _similarity(bank.get("reference"), gl.get("reference")),
    }


def _confidence(scores: Mapping[str, float]) -> float:
    weighted = (
        scores["amount"] * 0.40
        + scores["date_proximity"] * 0.20
        + scores["counterparty"] * 0.25
        + scores["reference"] * 0.15
    )
    return round(weighted, 4)


def _evidence(
    bank: Transaction,
    gl: Transaction,
    policy: MatchPolicy,
    *,
    method: str,
    auto_matched: bool,
) -> tuple[float, dict[str, object]]:
    scores = _field_scores(bank, gl, policy)
    confidence = _confidence(scores)
    amount_delta = _amount_distance(bank, gl)
    days = _date_distance(bank, gl)
    reasons = [
        "amount exact"
        if amount_delta == 0
        else f"amount differs by ${amount_delta:.2f}",
        "date exact" if days == 0 else f"dates are {days} days apart",
        f"counterparty similarity {scores['counterparty']:.2f}",
        f"reference similarity {scores['reference']:.2f}",
    ]
    if auto_matched:
        counterfactual = (
            f"would not auto-match if {method} requirements or policy v{policy.version} "
            "thresholds were not met"
        )
    else:
        failures: list[str] = []
        if amount_delta > policy.amount_tolerance:
            failures.append(
                f"amount delta ${amount_delta:.2f} exceeds ${policy.amount_tolerance:.2f} tolerance"
            )
        if days > policy.date_grace_days:
            failures.append(f"date gap {days}d exceeds {policy.date_grace_days}d grace")
        if scores["counterparty"] < policy.fuzzy_threshold:
            failures.append(
                f"counterparty {scores['counterparty']:.2f} < policy v{policy.version} threshold "
                f"{policy.fuzzy_threshold:.2f}"
            )
        counterfactual = "not auto-matched because " + "; ".join(
            failures or ["rule requirements were not met"]
        )
    return confidence, {
        "field_scores": scores,
        "reasons": reasons,
        "counterfactual": counterfactual,
        "source_rows": {"bank": bank.get("raw", {}), "gl": gl.get("raw", {})},
    }


def _same_currency(bank: Transaction, gl: Transaction) -> bool:
    return str(bank.get("currency", "USD")) == str(gl.get("currency", "USD"))


def _is_exact(bank: Transaction, gl: Transaction) -> bool:
    reference = _text(bank.get("reference"))
    counterparty = _text(bank.get("counterparty"))
    return (
        _same_currency(bank, gl)
        and _amount_distance(bank, gl) == 0
        and _date_distance(bank, gl) == 0
        and bool(reference or counterparty)
        and counterparty == _text(gl.get("counterparty"))
        and reference == _text(gl.get("reference"))
    )


def _is_rule_match(bank: Transaction, gl: Transaction, policy: MatchPolicy) -> bool:
    if not _same_currency(bank, gl):
        return False
    if _amount_distance(bank, gl) > policy.amount_tolerance:
        return False
    if _date_distance(bank, gl) > policy.date_grace_days:
        return False
    reference_exact = bool(_text(bank.get("reference"))) and _text(
        bank.get("reference")
    ) == _text(gl.get("reference"))
    counterparty_exact = bool(_text(bank.get("counterparty"))) and _text(
        bank.get("counterparty")
    ) == _text(gl.get("counterparty"))
    return reference_exact or counterparty_exact


def _is_fuzzy_match(bank: Transaction, gl: Transaction, policy: MatchPolicy) -> bool:
    if not _same_currency(bank, gl):
        return False
    if _amount_distance(bank, gl) > policy.amount_tolerance:
        return False
    if _date_distance(bank, gl) > policy.date_grace_days:
        return False
    scores = _field_scores(bank, gl, policy)
    identifying_score = max(scores["counterparty"], scores["reference"])
    return identifying_score >= policy.fuzzy_threshold


def _decision(
    bank: Transaction,
    gl: Transaction,
    policy: MatchPolicy,
    method: str,
    *,
    matched: bool,
) -> dict[str, object]:
    confidence, evidence = _evidence(
        bank, gl, policy, method=method, auto_matched=matched
    )
    return {
        "pair": [str(bank["id"]), str(gl["id"])],
        "status": "matched" if matched else "exception",
        "method": method,
        "confidence": confidence,
        "evidence": evidence,
    }


def _ambiguity_decision(
    bank: Transaction,
    gl_candidates: Sequence[Transaction],
    policy: MatchPolicy,
    method: str,
) -> dict[str, object]:
    candidate_ids = [str(candidate["id"]) for candidate in gl_candidates]
    scores = _field_scores(bank, gl_candidates[0], policy)
    candidate_count = len(gl_candidates)
    qualifier = "equally valid exact" if method == "exact" else f"qualifying {method}"
    return {
        "pair": None,
        "items": [str(bank["id"]), *candidate_ids],
        "status": "exception",
        "method": method,
        "confidence": _confidence(scores),
        "evidence": {
            "field_scores": scores,
            "reasons": [
                f"multiple {qualifier} GL candidates ({candidate_count})",
                f"candidate IDs: {', '.join(candidate_ids)}",
            ],
            "counterfactual": (
                f"not auto-matched because multiple {qualifier} GL candidates "
                f"({candidate_count}) create an ambiguity that requires review"
            ),
            "source_rows": {"bank": bank.get("raw", {})},
            "candidate_rows": [
                {
                    "id": str(candidate["id"]),
                    "source": "gl",
                    "raw": candidate.get("raw", {}),
                }
                for candidate in gl_candidates
            ],
        },
    }


def match_transactions(
    bank_transactions: Sequence[Transaction],
    gl_transactions: Sequence[Transaction],
    policy: MatchPolicy | None = None,
) -> list[dict[str, object]]:
    """Reconcile transactions in deterministic one-to-one passes.

    Exact candidates win over policy rules, which win over fuzzy candidates.
    Unmatched rows are returned as exceptions and always carry evidence. When a
    plausible counterpart exists, the exception retains that candidate pair so
    reviewers can inspect the failed thresholds rather than a context-free row.
    """

    active_policy = policy or MatchPolicy()
    banks = sorted(bank_transactions, key=lambda item: str(item["id"]))
    gls = sorted(gl_transactions, key=lambda item: str(item["id"]))
    remaining_bank = {str(item["id"]): item for item in banks}
    remaining_gl = {str(item["id"]): item for item in gls}
    decisions: list[dict[str, object]] = []
    ambiguities: dict[str, tuple[str, list[str]]] = {}

    def run_pass(method: str) -> None:
        candidates: list[tuple[float, str, str, Transaction, Transaction]] = []
        for bank_id, bank in remaining_bank.items():
            for gl_id, gl in remaining_gl.items():
                qualifies = (
                    _is_exact(bank, gl)
                    if method == "exact"
                    else _is_rule_match(bank, gl, active_policy)
                    if method == "rule"
                    else _is_fuzzy_match(bank, gl, active_policy)
                )
                if qualifies:
                    scores = _field_scores(bank, gl, active_policy)
                    candidates.append((_confidence(scores), bank_id, gl_id, bank, gl))
        bank_candidate_counts: dict[str, int] = {}
        gl_candidate_counts: dict[str, int] = {}
        for _, bank_id, gl_id, _, _ in candidates:
            bank_candidate_counts[bank_id] = bank_candidate_counts.get(bank_id, 0) + 1
            gl_candidate_counts[gl_id] = gl_candidate_counts.get(gl_id, 0) + 1
        for bank_id, candidate_count in bank_candidate_counts.items():
            if candidate_count <= 1 or bank_id in ambiguities:
                continue
            ambiguities[bank_id] = (
                method,
                sorted(
                    gl_id
                    for _, candidate_bank_id, gl_id, _, _ in candidates
                    if candidate_bank_id == bank_id
                ),
            )
        for _, bank_id, gl_id, bank, gl in sorted(
            candidates, key=lambda item: (-item[0], item[1], item[2])
        ):
            if bank_id not in remaining_bank or gl_id not in remaining_gl:
                continue
            # Multiple equally-valid candidates are a review signal, not an
            # invitation to choose whichever ID sorts first.
            if bank_candidate_counts[bank_id] != 1 or gl_candidate_counts[gl_id] != 1:
                continue
            decisions.append(_decision(bank, gl, active_policy, method, matched=True))
            del remaining_bank[bank_id]
            del remaining_gl[gl_id]

    for pass_name in ("exact", "rule", "fuzzy"):
        run_pass(pass_name)

    # Resolve ambiguous groups before generic review-candidate pairing so the
    # reason they were withheld survives into the evidence pack.
    for bank_id, (method, candidate_ids) in sorted(ambiguities.items()):
        if bank_id not in remaining_bank:
            continue
        available_candidates = [
            remaining_gl[candidate_id]
            for candidate_id in candidate_ids
            if candidate_id in remaining_gl
        ]
        if len(available_candidates) <= 1:
            continue
        decisions.append(
            _ambiguity_decision(
                remaining_bank[bank_id], available_candidates, active_policy, method
            )
        )
        del remaining_bank[bank_id]
        for candidate in available_candidates:
            del remaining_gl[str(candidate["id"])]

    candidate_pairs: list[tuple[float, str, str, Transaction, Transaction]] = []
    for bank_id, bank in remaining_bank.items():
        for gl_id, gl in remaining_gl.items():
            if not _same_currency(bank, gl):
                continue
            scores = _field_scores(bank, gl, active_policy)
            candidate_pairs.append((_confidence(scores), bank_id, gl_id, bank, gl))
    for score, bank_id, gl_id, bank, gl in sorted(
        candidate_pairs, key=lambda item: (-item[0], item[1], item[2])
    ):
        if score < active_policy.candidate_floor:
            break
        if bank_id not in remaining_bank or gl_id not in remaining_gl:
            continue
        decisions.append(_decision(bank, gl, active_policy, "fuzzy", matched=False))
        del remaining_bank[bank_id]
        del remaining_gl[gl_id]

    for transaction_id, transaction in sorted(remaining_bank.items()):
        decisions.append(_orphan_decision(transaction_id, transaction, "bank"))
    for transaction_id, transaction in sorted(remaining_gl.items()):
        decisions.append(_orphan_decision(transaction_id, transaction, "gl"))

    return decisions


def _orphan_decision(
    transaction_id: str, transaction: Transaction, source: str
) -> dict[str, object]:
    return {
        "pair": None,
        "status": "exception",
        "method": "rule",
        "confidence": 1.0,
        "items": [transaction_id],
        "evidence": {
            "field_scores": {
                "amount": 0.0,
                "date_proximity": 0.0,
                "counterparty": 0.0,
                "reference": 0.0,
            },
            "reasons": [
                f"no unused {('gl' if source == 'bank' else 'bank')} candidate found"
            ],
            "counterfactual": "not auto-matched because no counterpart exists",
            "source_rows": {source: transaction.get("raw", {})},
        },
    }
