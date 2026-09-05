from data.seed.generate_data import build


def test_seed_data_matches_frozen_benchmark_shape() -> None:
    data = build()

    assert len(data.bank) == 79
    assert len(data.gl) == 79
    assert len(data.labels) == 79
    exception_counts: dict[str, int] = {}
    for label in data.labels:
        truth = str(label["truth"])
        if truth != "matched":
            exception_counts[truth] = exception_counts.get(truth, 0) + 1
    assert exception_counts == {
        "TIMING_DIFF": 4,
        "DUPLICATE": 3,
        "MISSING_ENTRY": 3,
        "AMOUNT_MISMATCH": 4,
        "COUNTERPARTY_MISMATCH": 4,
    }


def test_every_generated_id_is_traceable_from_ground_truth() -> None:
    data = build()
    labeled_bank_ids = {str(label["bank_id"]) for label in data.labels}
    labeled_gl_ids = {
        str(gl_id)
        for label in data.labels
        for gl_id in (
            label.get("related_gl_ids")
            or ([label["gl_id"]] if label["gl_id"] is not None else [])
        )
    }

    assert labeled_bank_ids == {row["id"] for row in data.bank}
    assert labeled_gl_ids == {row["id"] for row in data.gl}
