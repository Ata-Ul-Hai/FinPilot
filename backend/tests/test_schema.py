import json
from pathlib import Path

from jsonschema import Draft202012Validator

from backend.app.ingest import ingest_pair
from backend.app.matcher import match_transactions

ROOT = Path(__file__).resolve().parents[2]


def test_public_contract_defines_every_section_four_shape() -> None:
    schema = json.loads((ROOT / "schema" / "close.schema.json").read_text())

    Draft202012Validator.check_schema(schema)
    assert {
        "transaction",
        "matchDecision",
        "exception",
        "policy",
        "closeRun",
        "groundTruthLabel",
    } <= schema["$defs"].keys()


def test_sample_transactions_and_decisions_satisfy_contract() -> None:
    schema = json.loads((ROOT / "schema" / "close.schema.json").read_text())
    validator = Draft202012Validator(schema)
    bank, gl = ingest_pair(
        ROOT / "data" / "sample" / "bank.csv",
        ROOT / "data" / "sample" / "gl.csv",
    )

    decisions = match_transactions(bank, gl)
    labels = [
        json.loads(line)
        for line in (ROOT / "eval" / "labels.jsonl").read_text().splitlines()
    ]

    for record in [*bank, *gl, *decisions, *labels]:
        validator.validate(record)


def test_downstream_exception_policy_and_close_run_shapes_validate() -> None:
    schema = json.loads((ROOT / "schema" / "close.schema.json").read_text())
    validator = Draft202012Validator(schema)
    evidence = {
        "field_scores": {
            "amount": 0.97,
            "date_proximity": 1.0,
            "counterparty": 1.0,
            "reference": 1.0,
        },
        "reasons": ["amount differs by $0.03"],
        "counterfactual": "not auto-resolved without explicit policy coverage",
        "source_rows": {"bank": {"id": "BNK-0012"}, "gl": {"id": "GL-0051"}},
    }
    records = [
        {
            "id": "EX-004",
            "kind": "AMOUNT_MISMATCH",
            "primary_kind": "AMOUNT_MISMATCH",
            "secondary_tags": ["possible-timing"],
            "items": ["BNK-0012", "GL-0051"],
            "disposition": "needs_review",
            "suggestion": "write off $0.03 under SHORT-PAY cap",
            "confidence": 0.91,
            "evidence": evidence,
        },
        {
            "id": "MATCH-01",
            "version": 2,
            "rule": {
                "fuzzy_threshold": 0.60,
                "amount_tolerance": 0.0,
                "date_grace_days": 0,
            },
            "created_by": "override EX-004 approved by controller",
            "diff_vs_previous": {"fuzzy_threshold": [0.80, 0.60]},
            "eval_impact": {"recall": [0.72, 0.96]},
        },
        {
            "run_id": "close-2026-08",
            "counts": {
                "bank": 79,
                "gl": 79,
                "matched": 61,
                "exceptions": 18,
                "auto_resolved": 5,
                "in_inbox": 13,
            },
            "checklist": [{"task": "cash reconciliation", "status": "done"}],
            "je_drafts": [
                {
                    "for": "MISSING_ENTRY BNK-0069",
                    "entry": {
                        "dr": "6120 Bank fees",
                        "cr": "1010 Cash",
                        "amount": 38.0,
                    },
                }
            ],
        },
    ]

    for record in records:
        validator.validate(record)
