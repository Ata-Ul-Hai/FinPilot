from data.seed.generate_data import build


def test_seed_data_matches_frozen_benchmark_shape() -> None:
    data = build()

    assert len(data.bank) == 79
    assert len(data.gl) == 83
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
