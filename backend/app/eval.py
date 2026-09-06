"""Deterministic evaluation harness comparing close decisions against frozen ground-truth labels."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from backend.app.ingest import ingest_pair
from backend.app.matcher import match_transactions
from backend.app.policies import Policy, load_policy

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BANK = ROOT / "data" / "sample" / "bank.csv"
DEFAULT_GL = ROOT / "data" / "sample" / "gl.csv"
DEFAULT_POLICY = ROOT / "backend" / "app" / "policies.json"
DEFAULT_LABELS = ROOT / "eval" / "labels.jsonl"

EXCEPTION_KINDS: list[str] = [
    "TIMING_DIFF",
    "DUPLICATE",
    "MISSING_ENTRY",
    "AMOUNT_MISMATCH",
    "COUNTERPARTY_MISMATCH",
]


def load_labels(labels_path: str | Path = DEFAULT_LABELS) -> list[dict[str, Any]]:
    path = Path(labels_path)
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def by_bank_id(records: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    indexed: dict[str, Mapping[str, Any]] = {}
    for record in records:
        pair = record.get("pair")
        items = record.get("items", [])
        bank_id = (
            pair[0]
            if pair
            else next((item for item in items if str(item).startswith("BNK-")), None)
        )
        if bank_id:
            indexed[str(bank_id)] = record
    return indexed


def is_kind_covered(
    kind: str,
    policy_or_policies: Policy | Mapping[str, Any] | Sequence[Policy | Mapping[str, Any]] | None,
) -> bool:
    """Determine whether an exception kind is covered/sanctioned by the active policy set.

    Coverage rules:
    - COUNTERPARTY_MISMATCH: covered iff any active policy has fuzzy_threshold < 0.80
    - TIMING_DIFF: covered iff any active policy has date_grace_days > 1
    - AMOUNT_MISMATCH: covered iff any active policy has amount_tolerance > 0
    - DUPLICATE and MISSING_ENTRY: NEVER coverable (auto-matching is always an error)
    """
    if not policy_or_policies:
        return False
    if kind in ("DUPLICATE", "MISSING_ENTRY"):
        return False

    policies: list[Any]
    if isinstance(policy_or_policies, (Policy, Mapping)):
        policies = [policy_or_policies]
    elif isinstance(policy_or_policies, Sequence):
        policies = list(policy_or_policies)
    else:
        return False

    for pol in policies:
        if isinstance(pol, Policy):
            fuzzy_threshold = pol.fuzzy_threshold
            date_grace_days = pol.date_grace_days
            amount_tolerance = pol.amount_tolerance
        elif isinstance(pol, Mapping):
            rule = pol.get("rule", pol)
            fuzzy_threshold = float(rule.get("fuzzy_threshold", 0.80))
            date_grace_days = int(rule.get("date_grace_days", 1))
            amount_tolerance = float(rule.get("amount_tolerance", 0.0))
        else:
            continue

        if kind == "COUNTERPARTY_MISMATCH" and fuzzy_threshold < 0.80:
            return True
        if kind == "TIMING_DIFF" and date_grace_days > 1:
            return True
        if kind == "AMOUNT_MISMATCH" and amount_tolerance > 0.0:
            return True

    return False


def evaluate_decisions(
    records: Sequence[Mapping[str, Any]],
    labels: Sequence[Mapping[str, Any]],
    policy_version: int = 1,
    policy: Policy | Mapping[str, Any] | Sequence[Policy | Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    records_by_bank = by_bank_id(records)

    tp = 0
    fp = 0
    fn = 0
    false_auto_closes = 0

    correct_by_kind: dict[str, int] = defaultdict(int)
    total_by_kind: dict[str, int] = defaultdict(int)

    for label in labels:
        bank_id = str(label["bank_id"])
        truth = str(label["truth"])
        record = records_by_bank.get(bank_id)

        is_matched = record is not None and record.get("status") == "matched"

        if truth == "matched":
            if is_matched and record.get("pair") == [bank_id, label.get("gl_id")]:
                tp += 1
            elif is_matched:
                fp += 1
                fn += 1
            else:
                fn += 1
        else:
            total_by_kind[truth] += 1
            if is_matched:
                if is_kind_covered(truth, policy):
                    # Policy-sanctioned human override/relaxation
                    tp += 1
                    correct_by_kind[truth] += 1
                else:
                    false_auto_closes += 1
                    fp += 1
            else:
                if record is not None and record.get("kind") == truth:
                    correct_by_kind[truth] += 1

    precision = round(tp / (tp + fp), 4) if (tp + fp) > 0 else 0.0
    recall = round(tp / (tp + fn), 4) if (tp + fn) > 0 else 0.0
    f1 = round((2 * precision * recall) / (precision + recall), 4) if (precision + recall) > 0 else 0.0

    per_kind_accuracy: dict[str, float] = {}
    for kind in EXCEPTION_KINDS:
        total = total_by_kind.get(kind, 0)
        per_kind_accuracy[kind] = round(correct_by_kind[kind] / total, 4) if total > 0 else 1.0


    inbox_size = sum(1 for r in records if r.get("status") != "matched")

    metrics = {
        "policy_version": policy_version,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "match_precision": precision,
        "match_recall": recall,
        "match_f1": f1,
        "false_auto_closes": false_auto_closes,
        "inbox_size": inbox_size,
        "classification_accuracy": per_kind_accuracy,
        "per_kind_accuracy": per_kind_accuracy,
        "total_exceptions_labeled": sum(total_by_kind.values()),
        "total_exceptions_correct": sum(correct_by_kind.values()),
    }
    return metrics


def run_evaluation(
    bank_path: str | Path = DEFAULT_BANK,
    gl_path: str | Path = DEFAULT_GL,
    policy_path_or_obj: str | Path | Policy = DEFAULT_POLICY,
    labels_path: str | Path = DEFAULT_LABELS,
) -> dict[str, Any]:
    bank, gl = ingest_pair(bank_path, gl_path)
    if isinstance(policy_path_or_obj, Policy):
        policy = policy_path_or_obj
    else:
        policy = load_policy(policy_path_or_obj)
    records = match_transactions(bank, gl, policy)
    labels = load_labels(labels_path)
    return evaluate_decisions(records, labels, policy_version=policy.version, policy=policy)


def format_markdown_table(metrics: dict[str, Any]) -> str:
    lines = [
        "### Evaluation Metrics",
        "",
        "| Metric | Value |",
        "| :--- | :--- |",
        f"| **Policy Version** | v{metrics['policy_version']} |",
        f"| **Match Precision** | {metrics['precision']:.4f} |",
        f"| **Match Recall** | {metrics['recall']:.4f} |",
        f"| **Match F1** | {metrics['f1']:.4f} |",
        f"| **False Auto-Closes** | {metrics['false_auto_closes']} |",
        f"| **Inbox Size** | {metrics['inbox_size']} |",
        f"| **Exception Accuracy** | {metrics['total_exceptions_correct']}/{metrics['total_exceptions_labeled']} |",
        "",
        "#### Per-Kind Exception Accuracy",
        "",
        "| Exception Kind | Accuracy |",
        "| :--- | :--- |",
    ]
    for kind, acc in metrics["classification_accuracy"].items():
        lines.append(f"| `{kind}` | {acc * 100:.1f}% |")

    if metrics["false_auto_closes"] > 0:
        lines.extend([
            "",
            f"**CRITICAL ALERT:** {metrics['false_auto_closes']} false auto-closes detected! Policy violates audit-ready rules.",
        ])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate close matching decisions against frozen ground-truth labels.")
    parser.add_argument("--bank", type=Path, default=DEFAULT_BANK, help="Path to canonical bank CSV")
    parser.add_argument("--gl", type=Path, default=DEFAULT_GL, help="Path to canonical GL CSV")
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY, help="Path to policy JSON")
    parser.add_argument("--labels", type=Path, default=DEFAULT_LABELS, help="Path to frozen labels.jsonl")
    parser.add_argument("--out", type=Path, default=None, help="Path to write evaluation JSON metrics")

    args = parser.parse_args()

    metrics = run_evaluation(
        bank_path=args.bank,
        gl_path=args.gl,
        policy_path_or_obj=args.policy,
        labels_path=args.labels,
    )

    table = format_markdown_table(metrics)
    print(table)

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
        print(f"\nWrote metrics to {args.out}")

    if metrics["false_auto_closes"] > 0:
        print(f"\nERROR: false_auto_closes = {metrics['false_auto_closes']} (> 0)!", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
