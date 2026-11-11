"""Adversarial end-to-end tests. Each test sends a payload that would have
exploited a vulnerability before Phase 1, and asserts the API rejects it."""
import pytest
from fastapi.testclient import TestClient

from app.web import create_app


@pytest.fixture(scope="module", autouse=True)
def _set_auth_env():
    import os
    os.environ.setdefault("GOOGLE_CLIENT_ID", "test-client-id")
    os.environ.setdefault("GOOGLE_CLIENT_SECRET", "test-client-secret")
    os.environ.setdefault("SESSION_SECRET", "x" * 32)
    os.environ.setdefault("APP_BASE_URL", "http://testserver")
    yield


@pytest.fixture(scope="module")
def client():
    from app.auth import require_user
    app = create_app()
    app.dependency_overrides[require_user] = lambda: "tester@example.com"
    return TestClient(app)


def test_workspace_endpoint_is_gone(client):
    res = client.get("/api/workspace")
    assert res.status_code == 404


def test_config_endpoint_does_not_leak_paths(client):
    res = client.get("/api/config")
    assert res.status_code == 200
    body = res.json()
    flat = repr(body)
    assert "datasets/" not in flat
    assert "parameters.json" not in flat
    assert "powertrain" not in body
    assert "tyre_model" not in body


def test_metadata_endpoint_does_not_leak_paths(client):
    res = client.get("/api/metadata")
    assert res.status_code == 200
    body = res.json()
    assert "datasets/" not in repr(body)


def test_tyre_verify_rejects_arbitrary_path(client):
    res = client.post("/api/tyre/verify", json={
        "lat_dataset": "../../etc/passwd",
        "long_dataset": "round_6_12psi",
    })
    assert res.status_code in (400, 422)


def test_tyre_verify_rejects_absolute_path(client):
    res = client.post("/api/tyre/verify", json={
        "lat_dataset": "/etc/passwd",
        "long_dataset": "round_6_12psi",
    })
    assert res.status_code in (400, 422)


def test_tyre_verify_accepts_registered_ids(client):
    res = client.post("/api/tyre/verify", json={
        "lat_dataset": "round_8_12psi",
        "long_dataset": "round_6_12psi",
    })
    assert res.status_code == 200


def test_sweep_rejects_param_dunder(client):
    res = client.post("/api/sweep/run", json={
        "param": "__class__",
        "values": "1,2,3",
    })
    assert res.status_code == 422


def test_sweep_rejects_unknown_param(client):
    res = client.post("/api/sweep/run", json={
        "param": "not_a_real_param",
        "values": "1,2,3",
    })
    assert res.status_code == 422


def test_sweep_rejects_unknown_track_id(client):
    res = client.post("/api/sweep/run", json={
        "param": "mass",
        "values": "200,250",
        "overrides": {"track_id": "../../etc"},
    })
    assert res.status_code == 422


def test_sweep_rejects_extra_overrides_field(client):
    res = client.post("/api/sweep/run", json={
        "param": "mass",
        "values": "200,250",
        "overrides": {"track": {"file_path": "/etc/passwd"}},
    })
    assert res.status_code == 422


def test_lap_rejects_extra_overrides_field(client):
    res = client.post("/api/lap/run", json={
        "overrides": {"track": {"file_path": "/etc/passwd"}},
    })
    assert res.status_code == 422


def test_lift_coast_rejects_oversized_power_list(client):
    res = client.post("/api/lift-coast/run", json={
        "power_limits_kw": [10.0] * 11,
    })
    assert res.status_code == 422


def test_lift_coast_rejects_out_of_range_power(client):
    res = client.post("/api/lift-coast/run", json={
        "power_limits_kw": [99999.0],
    })
    assert res.status_code == 422


def test_lift_coast_rejects_dunder_override(client):
    res = client.post("/api/lift-coast/run", json={
        "power_limits_kw": [10.0],
        "parameter_overrides": {"__class__": 1},
    })
    assert res.status_code == 422


def test_lap_response_does_not_leak_absolute_paths(client):
    res = client.post("/api/lap/run", json={})
    assert res.status_code == 200
    body = res.json()
    assert "track_file_path" in body
    track_field = body["track_file_path"]
    assert track_field, "track_file_path must be non-empty so the leak check is meaningful"
    assert "datasets/" not in track_field
    assert "/" not in track_field
    assert "\\" not in track_field


def test_datasets_endpoint_returns_registered_ids(client):
    res = client.get("/api/datasets")
    assert res.status_code == 200
    body = res.json()
    assert "FSUK" in body["tracks"]
    assert "round_8_12psi" in body["tyre_lateral"]
    assert "round_6_12psi" in body["tyre_longitudinal"]
