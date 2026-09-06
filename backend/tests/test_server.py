from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from backend.app.server import app, state, CloseState, POLICY_FILE, STATE_FILE
from backend.app.policies import load_policy, save_policy, Policy

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def reset_server_state(tmp_path, monkeypatch):
    # Save original policy
    original_policy = load_policy(POLICY_FILE)
    test_state_file = tmp_path / "test_run_state.json"
    test_policy_file = tmp_path / "test_policies.json"
    save_policy(original_policy, test_policy_file)

    monkeypatch.setattr("backend.app.server.STATE_FILE", test_state_file)
    monkeypatch.setattr("backend.app.server.POLICY_FILE", test_policy_file)

    # Re-initialize in-memory state
    state.policies = [original_policy.to_dict()]
    state.exceptions = []
    state.decisions = []
    state.transactions = []
    state.je_drafts = []
    state.baseline_evaluation = {}
    state.current_evaluation = {}
    state.run_reconciliation(save=False)

    yield

    # Restore original policy file
    save_policy(original_policy, POLICY_FILE)
    if test_state_file.exists():
        test_state_file.unlink()


def test_get_close_returns_full_snapshot_with_79_records() -> None:
    client = TestClient(app)
    response = client.get("/close")
    assert response.status_code == 200
    data = response.json()

    # Must contain both 'run' and 'decisions'
    assert "run" in data
    assert "decisions" in data
    assert "exceptions" in data
    assert "transactions" in data
    assert "policies" in data
    assert "review_rules" in data
    assert "evaluation" in data
    assert "commentary" in data

    # 61 matched decisions + 18 exceptions = 79 records
    assert len(data["decisions"]) == 61
    assert len(data["exceptions"]) == 18
    assert data["run"]["counts"]["matched"] == 61
    assert data["run"]["counts"]["exceptions"] == 18
    assert data["run"]["counts"]["bank"] == 79
    assert data["run"]["counts"]["gl"] == 79


def test_get_eval_baseline_precision_is_1() -> None:
    client = TestClient(app)
    response = client.get("/eval")
    assert response.status_code == 200
    data = response.json()

    assert "baseline" in data
    assert "current" in data
    assert data["baseline"]["precision"] == 1.0
    assert data["baseline"]["recall"] == 1.0
    assert data["baseline"]["f1"] == 1.0
    assert data["baseline"]["false_auto_closes"] == 0
    assert data["baseline"]["inbox_size"] == 18


def test_cors_header_present() -> None:
    client = TestClient(app)
    response = client.get(
        "/close",
        headers={"Origin": "http://localhost:5173"},
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") in (
        "http://localhost:5173",
        "*",
    )


def test_reclassify_exception() -> None:
    client = TestClient(app)
    # Find first exception
    snapshot = client.get("/close").json()
    first_ex = snapshot["exceptions"][0]
    ex_id = first_ex["id"]

    response = client.post(
        "/review/reclassify",
        json={"exception_id": ex_id, "primary_kind": "UNKNOWN"},
    )
    assert response.status_code == 200
    updated = response.json()
    updated_ex = next(e for e in updated["exceptions"] if e["id"] == ex_id)
    assert updated_ex["primary_kind"] == "UNKNOWN"


def test_approve_counterparty_mismatch_creates_v2_policy() -> None:
    client = TestClient(app)
    snapshot = client.get("/close").json()
    # Find counterparty mismatch exception
    cp_ex = next(
        e for e in snapshot["exceptions"]
        if e.get("primary_kind") == "COUNTERPARTY_MISMATCH" or e.get("kind") == "COUNTERPARTY_MISMATCH"
    )
    ex_id = cp_ex["id"]

    response = client.post(
        "/review",
        json={"exception_id": ex_id, "action": "approve", "applicable_policy_id": "MATCH-01"},
    )
    assert response.status_code == 200
    updated = response.json()

    # Check that MATCH-01 v2 was created
    latest_policy = updated["policies"][-1]
    assert latest_policy["version"] == 2
    assert latest_policy["diff_vs_previous"]["fuzzy_threshold"] == [0.80, 0.60]

    # Verify exception is resolved
    resolved = next(e for e in updated["exceptions"] if e["id"] == ex_id)
    assert resolved["disposition"] == "auto_resolved"


def test_bulk_approve_trust_gate_accept_and_reject() -> None:
    client = TestClient(app)
    snapshot = client.get("/close").json()

    # DUPLICATE exception (always rejected by gate)
    dup_ex = next(e for e in snapshot["exceptions"] if e.get("primary_kind") == "DUPLICATE")
    # MISSING_ENTRY fee <= $100 with confidence 1.0 (eligible under BANK-FEE)
    eligible_ex = next(e for e in snapshot["exceptions"] if e.get("id") == "EX-0017")
    # MISSING_ENTRY fee > $100 (rejected: exceeds cap)
    over_cap_ex = next(e for e in snapshot["exceptions"] if e.get("id") == "EX-0016")

    response = client.post(
        "/review/bulk-approve",
        json={"exception_ids": [dup_ex["id"], eligible_ex["id"], over_cap_ex["id"]]},
    )
    assert response.status_code == 200
    data = response.json()

    # Eligible bank fee approved
    assert eligible_ex["id"] in data["approved"]

    # Duplicate rejected
    rejected_ids = [r["id"] for r in data["rejected"]]
    assert dup_ex["id"] in rejected_ids
    assert any("duplicate" in r["reason"].lower() for r in data["rejected"] if r["id"] == dup_ex["id"])

    # Over-cap fee rejected
    assert over_cap_ex["id"] in rejected_ids
    assert any("exceeds" in r["reason"].lower() for r in data["rejected"] if r["id"] == over_cap_ex["id"])

