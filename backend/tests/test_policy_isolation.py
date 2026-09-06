from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from backend.app.server import app, state, POLICY_FILE, STATE_FILE
from backend.app.policies import load_policy, Policy

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
