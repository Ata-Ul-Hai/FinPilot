from backend.app.matcher import MatchPolicy, match_transactions


def transaction(
    transaction_id: str,
    source: str,
    *,
    amount: float = -100.0,
    date: str = "2026-08-31",
    counterparty: str = "Acme Freight",
    reference: str = "INV-4471",
) -> dict[str, object]:
    return {
        "id": transaction_id,
        "source": source,
        "date": date,
        "amount": amount,
        "currency": "USD",
        "counterparty": counterparty,
        "reference": reference,
        "raw": {"id": transaction_id},
    }


def test_exact_match_has_scored_traceable_evidence() -> None:
    decisions = match_transactions(
        [transaction("BNK-0007", "bank")], [transaction("GL-0031", "gl")]
    )

    assert decisions[0]["status"] == "matched"
    assert decisions[0]["method"] == "exact"
    assert decisions[0]["confidence"] == 1.0
    assert decisions[0]["evidence"]["field_scores"] == {
        "amount": 1.0,
        "date_proximity": 1.0,
        "counterparty": 1.0,
        "reference": 1.0,
    }
    assert decisions[0]["evidence"]["source_rows"]["bank"] == {"id": "BNK-0007"}


def test_strict_policy_flags_counterparty_typo_with_counterfactual() -> None:
    bank = transaction("BNK-0007", "bank", reference="")
    gl = transaction("GL-0031", "gl", counterparty="ACM FRT", reference="")

    decision = match_transactions([bank], [gl], MatchPolicy(fuzzy_threshold=0.80))[0]

    assert decision["status"] == "exception"
    assert decision["method"] == "fuzzy"
    assert decision["pair"] == ["BNK-0007", "GL-0031"]
    assert decision["evidence"]["field_scores"]["counterparty"] < 0.80
    assert "counterparty" in decision["evidence"]["counterfactual"]


def test_lower_threshold_turns_review_candidate_into_fuzzy_match() -> None:
    bank = transaction("BNK-0007", "bank", reference="")
    gl = transaction("GL-0031", "gl", counterparty="ACM FRT", reference="")

    decision = match_transactions([bank], [gl], MatchPolicy(fuzzy_threshold=0.60))[0]

    assert decision["status"] == "matched"
    assert decision["method"] == "fuzzy"


def test_blank_identifiers_are_not_exact_match_evidence() -> None:
    bank = transaction("BNK-1", "bank", counterparty="", reference="")
    gl = transaction("GL-1", "gl", counterparty="", reference="")

    decision = match_transactions([bank], [gl])[0]

    assert decision["status"] == "exception"
    assert decision["evidence"]["field_scores"]["counterparty"] == 0.0
    assert decision["evidence"]["field_scores"]["reference"] == 0.0


def test_rule_match_obeys_amount_and_date_policy() -> None:
    bank = transaction("BNK-1", "bank", date="2026-08-31", amount=100.0)
    gl = transaction("GL-1", "gl", date="2026-09-02", amount=100.03)

    strict = match_transactions([bank], [gl], MatchPolicy())
    permissive = match_transactions(
        [bank], [gl], MatchPolicy(amount_tolerance=0.05, date_grace_days=3)
    )

    assert strict[0]["status"] == "exception"
    assert "amount delta" in strict[0]["evidence"]["counterfactual"]
    assert permissive[0]["status"] == "matched"
    assert permissive[0]["method"] == "rule"


def test_ambiguous_duplicates_are_not_auto_matched() -> None:
    bank = [transaction("BNK-1", "bank")]
    gl = [transaction("GL-2", "gl"), transaction("GL-1", "gl")]

    decisions = match_transactions(bank, gl)

    assert decisions[0]["pair"] == ["BNK-1", "GL-1"]
    assert decisions[0]["status"] == "exception"
    assert decisions[1]["pair"] is None
    assert decisions[1]["items"] == ["GL-2"]
    assert decisions[1]["evidence"]
    assert not any(item["status"] == "matched" for item in decisions)


def test_every_decision_has_evidence_even_for_orphans() -> None:
    decisions = match_transactions(
        [transaction("BNK-1", "bank")],
        [transaction("GL-1", "gl", amount=999), transaction("GL-2", "gl", amount=777)],
    )

    assert decisions
    assert all(decision.get("evidence") for decision in decisions)
    assert all(decision["evidence"].get("counterfactual") for decision in decisions)


def test_benchmark_acceptance_61_exact_and_four_typo_exceptions() -> None:
    banks = []
    gls = []
    for index in range(1, 62):
        kwargs = {
            "amount": float(index * -10),
            "counterparty": f"Vendor {index}",
            "reference": f"INV-{index:04d}",
        }
        banks.append(transaction(f"BNK-{index:04d}", "bank", **kwargs))
        gls.append(transaction(f"GL-{index:04d}", "gl", **kwargs))
    for offset, (left, right) in enumerate(
        [
            ("Acme Freight", "ACM FRT"),
            ("Northstar Software", "NRTHSTR SFT"),
            ("Blue River Logistics", "BL RVR LGSTCS"),
            ("Beacon Consulting", "BCN CNSLTNG"),
        ],
        start=62,
    ):
        banks.append(
            transaction(
                f"BNK-{offset:04d}",
                "bank",
                amount=float(offset * -10),
                counterparty=left,
                reference="",
            )
        )
        gls.append(
            transaction(
                f"GL-{offset:04d}",
                "gl",
                amount=float(offset * -10),
                counterparty=right,
                reference="",
            )
        )

    decisions = match_transactions(banks, gls, MatchPolicy(fuzzy_threshold=0.80))

    exact = [
        item
        for item in decisions
        if item["method"] == "exact" and item["status"] == "matched"
    ]
    exceptions = [item for item in decisions if item["status"] == "exception"]
    assert len(exact) == 61
    assert len(exceptions) == 4
    assert all(
        item["evidence"]["field_scores"]["counterparty"] < 0.80 for item in exceptions
    )
    assert all(item["evidence"]["source_rows"] for item in exceptions)
