"""End-to-end tests for the auth gate."""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="session", autouse=True)
def _set_auth_env():
    import os
    os.environ.setdefault("GOOGLE_CLIENT_ID", "test-client-id")
    os.environ.setdefault("GOOGLE_CLIENT_SECRET", "test-client-secret")
    os.environ.setdefault("SESSION_SECRET", "x" * 32)
    os.environ.setdefault("APP_BASE_URL", "http://testserver")
    yield


@pytest.fixture
def unauthed_client():
    from app.web import create_app
    return TestClient(create_app(), raise_server_exceptions=False)


@pytest.fixture
def authed_client():
    from app.auth import require_user
    from app.web import create_app
    app = create_app()
    app.dependency_overrides[require_user] = lambda: "tester@example.com"
    return TestClient(app)


def test_health_is_open_to_anyone(unauthed_client):
    res = unauthed_client.get("/api/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


def test_login_page_renders(unauthed_client):
    res = unauthed_client.get("/login")
    assert res.status_code == 200
    assert "Sign in with Google" in res.text


def test_root_redirects_to_login_when_unauthed(unauthed_client):
    res = unauthed_client.get("/", follow_redirects=False)
    assert res.status_code == 303
    assert res.headers["location"] == "/login"


def test_api_returns_401_unauthed(unauthed_client):
    for path in ("/api/datasets", "/api/metadata", "/api/parameters", "/api/config", "/api/me"):
        res = unauthed_client.get(path)
        assert res.status_code == 401, f"{path} should require auth"


def test_api_post_returns_401_unauthed(unauthed_client):
    res = unauthed_client.post("/api/lap/run", json={})
    assert res.status_code == 401


def test_authed_client_can_call_protected_routes(authed_client):
    res = authed_client.get("/api/datasets")
    assert res.status_code == 200
    assert "tracks" in res.json()


def test_me_returns_email_when_authed(authed_client):
    res = authed_client.get("/api/me")
    assert res.status_code == 200
    assert res.json() == {"email": "tester@example.com"}


def test_logout_clears_session_and_redirects(authed_client):
    res = authed_client.post("/logout", follow_redirects=False)
    assert res.status_code == 303
    assert res.headers["location"] == "/login"


@pytest.mark.skip(reason="Requires network for Google OIDC discovery")
def test_auth_start_redirects_to_google(unauthed_client):
    res = unauthed_client.get("/auth/start", follow_redirects=False)
    assert res.status_code in (302, 303, 307)
    assert "accounts.google.com" in res.headers.get("location", "")
