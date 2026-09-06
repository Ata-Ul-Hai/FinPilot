import json
from pathlib import Path

from backend.app.matcher import main

ROOT = Path(__file__).resolve().parents[2]


def test_cli_writes_decisions_and_prints_summary(tmp_path, capsys) -> None:
    output = tmp_path / "decisions.json"

    result = main(
        [
            "--bank",
            str(ROOT / "data" / "sample" / "bank.csv"),
            "--gl",
            str(ROOT / "data" / "sample" / "gl.csv"),
            "--out",
            str(output),
        ]
    )

    records = json.loads(output.read_text())
    summary = capsys.readouterr().out
    assert result == 0
    assert len(records) == 79
    assert "exact: 61" in summary
    assert "TIMING_DIFF: 4" in summary
    assert "DUPLICATE: 3" in summary
    assert "MISSING_ENTRY: 3" in summary
    assert "AMOUNT_MISMATCH: 4" in summary
    assert "COUNTERPARTY_MISMATCH: 4" in summary
