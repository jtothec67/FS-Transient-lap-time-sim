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
def lap_result():
    from app.auth import require_user
    app = create_app()
    app.dependency_overrides[require_user] = lambda: "tester@example.com"
    client = TestClient(app)
    res = client.post('/api/lap/run', json={})
    assert res.status_code == 200
    return res.json()


def test_run_lap_returns_telemetry_key(lap_result):
    assert 'telemetry' in lap_result


def test_telemetry_arrays_all_same_length(lap_result):
    telem = lap_result['telemetry']
    n = len(telem['distances_m'])
    assert n > 0
    assert len(telem['speeds_kmh']) == n
    assert len(telem['g_lat']) == n
    assert len(telem['g_long']) == n


def test_telemetry_distances_start_at_zero(lap_result):
    telem = lap_result['telemetry']
    assert telem['distances_m'][0] == pytest.approx(0.0)
    assert telem['distances_m'][-1] > 0


def test_telemetry_speeds_non_negative(lap_result):
    telem = lap_result['telemetry']
    assert all(s >= 0 for s in telem['speeds_kmh'])
    assert max(telem['speeds_kmh']) > 0


def test_telemetry_g_arrays_padded_at_index_zero(lap_result):
    telem = lap_result['telemetry']
    assert telem['g_lat'][0] == pytest.approx(0.0)
    assert telem['g_long'][0] == pytest.approx(0.0)
