from backend.app.matcher import match_transactions
from backend.app.policies import Policy


def transaction(
    transaction_id: str,
    source: str,
    *,
    amount: float = -100.0,
    posted: str = "2026-08-31",
    counterparty: str = "Acme Freight",
    reference: str = "INV-4471",
) -> dict[str, object]:
    return {
        "id": transaction_id,
        "source": source,
        "date": posted,
        "amount": amount,
        "currency": "USD",
        "counterparty": counterparty,
        "reference": reference,
        "raw": {"id": transaction_id},
    }


def test_exact_requires_reference_amount_and_date_within_one_day() -> None:
    bank = transaction("BNK-1", "bank", posted="2026-08-31")
    gl = transaction(
        "GL-1",
        "gl",
        posted="2026-09-01",
        counterparty="Counterparty spelling does not gate exact",
    )

    record = match_transactions([bank], [gl], Policy())[0]

    assert record["pair"] == ["BNK-1", "GL-1"]
    assert record["method"] == "exact"
    assert record["confidence"] == 1.0
    assert record["evidence"]["reasons"]


def test_reference_rules_classify_amount_and_timing_exceptions() -> None:
    bank = [
        transaction("BNK-1", "bank", amount=-100.0, reference="INV-AMOUNT"),
        transaction("BNK-2", "bank", posted="2026-08-31", reference="INV-TIME"),
    ]
    gl = [
        transaction("GL-1", "gl", amount=-99.97, reference="INV-AMOUNT"),
        transaction("GL-2", "gl", posted="2026-09-03", reference="INV-TIME"),
    ]

    records = match_transactions(bank, gl, Policy())

    assert [record["kind"] for record in records] == [
        "AMOUNT_MISMATCH",
        "TIMING_DIFF",
    ]
    assert all(record["evidence"]["counterfactual"] for record in records)


def test_duplicate_retains_all_candidates_and_ambiguity_evidence() -> None:
    bank = [transaction("BNK-1", "bank")]
    gl = [transaction("GL-2", "gl"), transaction("GL-1", "gl")]

    record = match_transactions(bank, gl, Policy())[0]

    assert record["kind"] == "DUPLICATE"
    assert record["items"] == ["BNK-1", "GL-1", "GL-2"]
    assert (
        "multiple equally valid GL candidates" in record["evidence"]["counterfactual"]
    )
    assert [item["id"] for item in record["evidence"]["candidate_rows"]] == [
        "GL-1",
        "GL-2",
    ]


def test_fuzzy_threshold_matches_or_escalates_counterparty() -> None:
    bank = transaction("BNK-1", "bank", reference="")
    gl = transaction("GL-1", "gl", counterparty="Acme Freigt", reference="")

    matched = match_transactions([bank], [gl], Policy(fuzzy_threshold=0.80))[0]
    escalated = match_transactions([bank], [gl], Policy(fuzzy_threshold=0.95))[0]

    assert matched["status"] == "matched"
    assert matched["method"] == "fuzzy"
    assert 0 <= matched["confidence"] <= 1
    assert escalated["kind"] == "COUNTERPARTY_MISMATCH"
    assert "below policy" in escalated["evidence"]["counterfactual"]


def test_no_safe_candidate_is_missing_entry() -> None:
    record = match_transactions(
        [transaction("BNK-1", "bank", amount=-100.0)],
        [transaction("GL-1", "gl", amount=-999.0, reference="UNRELATED")],
        Policy(),
    )[0]

    assert record["kind"] == "MISSING_ENTRY"
    assert record["items"] == ["BNK-1"]
    assert record["evidence"]["source_rows"]["bank"] == {"id": "BNK-1"}


def test_every_output_record_has_complete_evidence() -> None:
    records = match_transactions(
        [
            transaction("BNK-1", "bank", reference="INV-1"),
            transaction("BNK-2", "bank", amount=-200.0, reference=""),
        ],
        [transaction("GL-1", "gl", reference="INV-1")],
        Policy(),
    )

    for record in records:
        evidence = record["evidence"]
        assert set(evidence["field_scores"]) == {
            "amount",
            "date_proximity",
            "counterparty",
            "reference",
        }
        assert evidence["reasons"]
        assert evidence["counterfactual"]
