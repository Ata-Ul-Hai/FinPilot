import json
from collections import Counter
from pathlib import Path

from backend.app.ingest import ingest_pair
from backend.app.matcher import match_transactions
from backend.app.policies import load_policy

ROOT = Path(__file__).resolve().parents[2]


def _labels() -> list[dict[str, object]]:
    with (ROOT / "eval" / "labels.jsonl").open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream]


def _by_bank_id(records: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    indexed: dict[str, dict[str, object]] = {}
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


def test_frozen_labels_match_sample_results_exactly() -> None:
    bank, gl = ingest_pair(
        ROOT / "data" / "sample" / "bank.csv",
        ROOT / "data" / "sample" / "gl.csv",
    )
    records = match_transactions(bank, gl, load_policy())
    records_by_bank = _by_bank_id(records)
    labels = _labels()

    assert len(records_by_bank) == len(labels) == 79
    expected_counts = Counter(str(label["truth"]) for label in labels)
    actual_counts = Counter(
        "matched" if record.get("status") == "matched" else str(record["kind"])
        for record in records
    )
    assert (
        expected_counts
        == actual_counts
        == {
            "matched": 61,
            "TIMING_DIFF": 4,
            "DUPLICATE": 3,
            "MISSING_ENTRY": 3,
            "AMOUNT_MISMATCH": 4,
            "COUNTERPARTY_MISMATCH": 4,
        }
    )

    for label in labels:
        record = records_by_bank[str(label["bank_id"])]
        assert record["evidence"]["reasons"]
        assert record["evidence"]["counterfactual"]
        assert record["evidence"]["source_rows"]
        if label["truth"] == "matched":
            assert record["pair"] == [label["bank_id"], label["gl_id"]]
            assert record["method"] == "exact"
            assert record["confidence"] == 1.0
        else:
            assert record["kind"] == label["truth"]
            assert label["bank_id"] in record["items"]
            if label["gl_id"] is not None:
                assert label["gl_id"] in record["items"]
            if label["truth"] == "DUPLICATE":
                assert set(label["related_gl_ids"]) == set(record["items"][1:])


def test_all_outputs_have_evidence_and_at_least_61_exact_matches() -> None:
    bank, gl = ingest_pair(
        ROOT / "data" / "sample" / "bank.csv",
        ROOT / "data" / "sample" / "gl.csv",
    )
    records = match_transactions(bank, gl, load_policy())

    assert sum(record.get("method") == "exact" for record in records) >= 61
    assert all(record.get("evidence") for record in records)
