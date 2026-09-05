import json
from pathlib import Path

from backend.app.ingest import ingest_pair
from backend.app.matcher import MatchPolicy, match_transactions

ROOT = Path(__file__).resolve().parents[2]


def _labels() -> list[dict[str, object]]:
    with (ROOT / "eval" / "labels.jsonl").open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream]


def _decision_by_bank_id(
    decisions: list[dict[str, object]],
) -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    for decision in decisions:
        pair = decision.get("pair")
        items = decision.get("items", [])
        bank_id = (
            pair[0]
            if pair
            else next((item for item in items if str(item).startswith("BNK-")), None)
        )
        if bank_id:
            result[str(bank_id)] = decision
    return result


def test_frozen_sample_acceptance_and_labeled_review_evidence() -> None:
    bank, gl = ingest_pair(
        ROOT / "data" / "sample" / "bank.csv",
        ROOT / "data" / "sample" / "gl.csv",
    )
    decisions = match_transactions(bank, gl, MatchPolicy(fuzzy_threshold=0.80))
    decisions_by_bank = _decision_by_bank_id(decisions)
    labels = _labels()

    assert len(bank) == 79
    assert len(gl) == 79
    assert (
        sum(
            decision["status"] == "matched" and decision["method"] == "exact"
            for decision in decisions
        )
        >= 61
    )
    assert all(decision.get("evidence") for decision in decisions)

    typo_labels = [
        label for label in labels if label["truth"] == "COUNTERPARTY_MISMATCH"
    ]
    assert len(typo_labels) == 4
    for label in typo_labels:
        decision = decisions_by_bank[str(label["bank_id"])]
        assert decision["pair"] == [label["bank_id"], label["gl_id"]]
        assert decision["status"] == "exception"
        assert decision["evidence"]["field_scores"]["counterparty"] < 0.80
        assert "counterparty" in decision["evidence"]["counterfactual"]
        assert decision["evidence"]["source_rows"]

    duplicate_labels = [label for label in labels if label["truth"] == "DUPLICATE"]
    assert len(duplicate_labels) == 3
    for label in duplicate_labels:
        decision = decisions_by_bank[str(label["bank_id"])]
        assert decision["pair"] is None
        assert decision["method"] == "exact"
        assert label["gl_id"] in decision["items"]
        assert set(label["related_gl_ids"]) == set(decision["items"][1:])
        assert (
            "multiple equally valid exact GL candidates"
            in decision["evidence"]["counterfactual"]
        )
        assert len(decision["evidence"]["candidate_rows"]) == 2

    labeled_bank_ids = {str(label["bank_id"]) for label in labels}
    labeled_gl_ids = {
        str(gl_id)
        for label in labels
        for gl_id in (
            label.get("related_gl_ids")
            or ([label["gl_id"]] if label["gl_id"] is not None else [])
        )
    }
    assert labeled_bank_ids == {str(item["id"]) for item in bank}
    assert labeled_gl_ids == {str(item["id"]) for item in gl}
