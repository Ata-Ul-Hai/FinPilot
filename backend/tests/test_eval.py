from pathlib import Path
from backend.app.eval import run_evaluation

ROOT = Path(__file__).resolve().parents[2]


def test_baseline_eval_metrics() -> None:
    metrics = run_evaluation(
        bank_path=ROOT / "data" / "sample" / "bank.csv",
        gl_path=ROOT / "data" / "sample" / "gl.csv",
        policy_path_or_obj=ROOT / "backend" / "app" / "policies.json",
        labels_path=ROOT / "eval" / "labels.jsonl",
    )

    assert metrics["policy_version"] == 1
    assert metrics["precision"] == 1.0
    assert metrics["recall"] == 1.0
    assert metrics["f1"] == 1.0
    assert metrics["false_auto_closes"] == 0
    assert metrics["inbox_size"] == 18
    assert metrics["total_exceptions_correct"] == 18
    assert metrics["total_exceptions_labeled"] == 18

    assert metrics["classification_accuracy"] == {
        "TIMING_DIFF": 1.0,
        "DUPLICATE": 1.0,
        "MISSING_ENTRY": 1.0,
        "AMOUNT_MISMATCH": 1.0,
        "COUNTERPARTY_MISMATCH": 1.0,
    }
