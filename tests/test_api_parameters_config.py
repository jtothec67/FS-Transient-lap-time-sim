import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import pytest
from app.services.lap_service import get_parameters, get_config
from fastapi.testclient import TestClient
from app.web import create_app


@pytest.fixture(scope="module", autouse=True)
def _set_auth_env():
    os.environ.setdefault("GOOGLE_CLIENT_ID", "test-client-id")
    os.environ.setdefault("GOOGLE_CLIENT_SECRET", "test-client-secret")
    os.environ.setdefault("SESSION_SECRET", "x" * 32)
    os.environ.setdefault("APP_BASE_URL", "http://testserver")
    yield


def _authed_client():
    from app.auth import require_user
    app = create_app()
    app.dependency_overrides[require_user] = lambda: "tester@example.com"
    return TestClient(app)


def test_get_parameters_excludes_comments():
    data = get_parameters()
    assert "_comments" not in data
    assert "general" in data
    assert "aerodynamics" in data
    assert "geometry" in data
    assert "vehicle_dynamics" in data
    assert "drivetrain" in data


def test_get_config_has_expected_keys():
    data = get_config()
    assert "track" in data
    assert "powertrain" in data
    assert "tyre_model" in data


def test_http_get_config_sanitised_shape():
    client = _authed_client()
    resp = client.get("/api/config")
    assert resp.status_code == 200
    data = resp.json()
    assert set(data.keys()) == {"full_telemetry_mode", "solver", "ambient_conditions", "datasets"}
    assert "use_rollover_speed_cap" in data["solver"]
    assert "max_brake_decel_g" in data["solver"]
    assert "air_density" in data["ambient_conditions"]
    assert "track" not in data
    assert "powertrain" not in data
    assert "tyre_model" not in data
    assert "vehicle_parameters" not in data

    # The datasets block carries labels and ids, never raw file paths.
    ds = data["datasets"]
    assert set(ds.keys()) == {"powertrain", "track", "tyre_lateral", "tyre_longitudinal"}
    for key in ds:
        assert "label" in ds[key]
        # No path-looking values should leak through.
        for v in ds[key].values():
            assert v is None or "/" not in str(v) and "\\" not in str(v)


def test_http_get_parameters():
    client = _authed_client()
    resp = client.get("/api/parameters")
    assert resp.status_code == 200
    data = resp.json()
    assert "_comments" not in data
    assert "general" in data


def test_http_get_config_returns_200():
    client = _authed_client()
    resp = client.get("/api/config")
    assert resp.status_code == 200


def test_http_post_lap_run_null_body():
    client = _authed_client()
    resp = client.post("/api/lap/run", json={})
    assert resp.status_code == 200
    data = resp.json()
    assert "lap_time_s" in data
