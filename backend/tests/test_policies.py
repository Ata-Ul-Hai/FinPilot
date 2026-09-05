import json

import pytest

from backend.app.policies import Policy, PolicyError, load_policy, save_policy


def test_default_match_policy_loads_from_json() -> None:
    policy = load_policy()

    assert policy.id == "MATCH-01"
    assert policy.version == 1
    assert policy.fuzzy_threshold == 0.80
    assert policy.amount_tolerance == 0.0
    assert policy.date_grace_days == 1


def test_policy_round_trips_through_json(tmp_path) -> None:
    path = tmp_path / "policy.json"
    policy = Policy(
        version=2,
        fuzzy_threshold=0.65,
        date_grace_days=5,
        created_by="controller override",
        diff_vs_previous={"fuzzy_threshold": [0.80, 0.65]},
    )

    save_policy(policy, path)

    assert load_policy(path) == policy
    assert json.loads(path.read_text())["rule"]["date_grace_days"] == 5


def test_invalid_policy_is_rejected(tmp_path) -> None:
    path = tmp_path / "policy.json"
    path.write_text('{"id": "MATCH-01"}')

    with pytest.raises(PolicyError, match="invalid policy"):
        load_policy(path)
