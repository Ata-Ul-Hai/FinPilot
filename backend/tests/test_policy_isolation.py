from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from backend.app.server import app, state, CloseState, POLICY_FILE, STATE_FILE
from backend.app.policies import load_policy, Policy
from backend.app.eval import evaluate_decisions, format_markdown_table

ROOT = Path(__file__).resolve().parents[2]


def test_tracked_policy_file_is_never_mutated_on_approval(tmp_path, monkeypatch) -> None:
    test_state_file = tmp_path / "test_run_state.json"
    monkeypatch.setattr("backend.app.server.STATE_FILE", test_state_file)

    # Capture initial bytes of backend/app/policies.json
    initial_bytes = POLICY_FILE.read_bytes()

    # Reset in-memory state
    v1_policy = load_policy(POLICY_FILE)
    state.policies = [v1_policy.to_dict()]
    state.exceptions = []
    state.decisions = []
    state.transactions = []
    state.je_drafts = []
    state.baseline_evaluation = {}
    state.current_evaluation = {}
    state.run_reconciliation(save=False)

    client = TestClient(app)
    snapshot = client.get("/close").json()
    cp_ex = next(
        e for e in snapshot["exceptions"]
        if e.get("primary_kind") == "COUNTERPARTY_MISMATCH" or e.get("kind") == "COUNTERPARTY_MISMATCH"
    )

    # Approve counterparty mismatch (creates v2 in memory and in STATE_FILE)
    response = client.post(
        "/review",
        json={"exception_id": cp_ex["id"], "action": "approve", "applicable_policy_id": "MATCH-01"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["policies"][-1]["version"] == 2

    # Assert backend/app/policies.json was NOT mutated
    assert POLICY_FILE.read_bytes() == initial_bytes


def test_restart_simulation_preserves_baseline_and_eval_metrics(tmp_path, monkeypatch) -> None:
    test_state_file = tmp_path / "test_run_state.json"
    monkeypatch.setattr("backend.app.server.STATE_FILE", test_state_file)

    # Reset state to cold start
    v1_policy = load_policy(POLICY_FILE)
    state.policies = [v1_policy.to_dict()]
    state.exceptions = []
    state.decisions = []
    state.transactions = []
    state.je_drafts = []
    state.baseline_evaluation = {}
    state.current_evaluation = {}
    state.run_reconciliation(save=True)

    client = TestClient(app)
    snapshot = client.get("/close").json()
    cp_ex = next(
        e for e in snapshot["exceptions"]
        if e.get("primary_kind") == "COUNTERPARTY_MISMATCH" or e.get("kind") == "COUNTERPARTY_MISMATCH"
    )

    # Approve COUNTERPARTY_MISMATCH -> bumps policy to v2
    client.post(
        "/review",
        json={"exception_id": cp_ex["id"], "action": "approve", "applicable_policy_id": "MATCH-01"},
    )

    # Simulate restart by loading state from disk into fresh state
    state.load_from_disk()
    fresh_client = TestClient(app)

    eval_data = fresh_client.get("/eval").json()
    baseline = eval_data["baseline"]
    current = eval_data["current"]

    assert baseline["policy_version"] == 1
    assert baseline["precision"] == 1.0
    assert baseline["false_auto_closes"] == 0

    policies_data = fresh_client.get("/policies").json()
    versions = [p["version"] for p in policies_data]
    assert 2 in versions
    assert current["policy_version"] == 2
    assert current["false_auto_closes"] == 0
    assert current["recall"] == 1.0


def test_eval_semantics_sanctioned_match_vs_duplicate_critical_alert() -> None:
    # 1. Sanctioned counterparty match under fuzzy_threshold 0.60
    v2_policy = Policy(
        id="MATCH-01",
        version=2,
        fuzzy_threshold=0.60,
        amount_tolerance=0.0,
        date_grace_days=1,
    )
    labels = [
        {"bank_id": "BNK-0001", "gl_id": "GL-0001", "truth": "matched"},
        {"bank_id": "BNK-0076", "gl_id": "GL-0076", "truth": "COUNTERPARTY_MISMATCH"},
    ]
    # Both are matched
    records = [
        {"pair": ["BNK-0001", "GL-0001"], "status": "matched"},
        {"pair": ["BNK-0076", "GL-0076"], "status": "matched"},
    ]
    sanctioned_eval = evaluate_decisions(records, labels, policy_version=2, policy=v2_policy)
    assert sanctioned_eval["false_auto_closes"] == 0
    assert sanctioned_eval["precision"] == 1.0

    # 2. Auto-matched DUPLICATE row (never coverable)
    labels_with_dup = [
        {"bank_id": "BNK-0001", "gl_id": "GL-0001", "truth": "matched"},
        {"bank_id": "BNK-0066", "gl_id": "GL-0066", "truth": "DUPLICATE"},
    ]
    records_with_dup = [
        {"pair": ["BNK-0001", "GL-0001"], "status": "matched"},
        {"pair": ["BNK-0066", "GL-0066"], "status": "matched"},
    ]
    dup_eval = evaluate_decisions(records_with_dup, labels_with_dup, policy_version=2, policy=v2_policy)
    assert dup_eval["false_auto_closes"] == 1
    markdown = format_markdown_table(dup_eval)
    assert "CRITICAL ALERT" in markdown
