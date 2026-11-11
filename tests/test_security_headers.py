"""Tests for security response headers middleware."""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _set_auth_env(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "test-client-secret")
    monkeypatch.setenv("SESSION_SECRET", "x" * 32)
    monkeypatch.setenv("APP_BASE_URL", "http://testserver")


@pytest.fixture
def client():
    from app.web import create_app
    return TestClient(create_app(), raise_server_exceptions=False)


def test_health_has_x_frame_options(client):
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.headers.get("x-frame-options") == "DENY"


def test_health_has_x_content_type_options(client):
    res = client.get("/api/health")
    assert res.headers.get("x-content-type-options") == "nosniff"


def test_health_has_referrer_policy(client):
    res = client.get("/api/health")
    assert res.headers.get("referrer-policy") == "same-origin"


def test_health_has_permissions_policy(client):
    res = client.get("/api/health")
    assert res.headers.get("permissions-policy") == "camera=(), microphone=(), geolocation=()"


def test_health_has_csp(client):
    res = client.get("/api/health")
    csp = res.headers.get("content-security-policy", "")
    assert "default-src" in csp
    assert "'self'" in csp


def test_no_hsts_over_http(client):
    """HSTS must not be set when running over plain HTTP."""
    res = client.get("/api/health")
    # TestClient uses http:// by default
    assert "strict-transport-security" not in res.headers


def test_hsts_set_over_https_via_forwarded_proto():
    """HSTS must be set when X-Forwarded-Proto is https (Fly.io header)."""
    from app.web import create_app
    app = create_app()
    client = TestClient(app, raise_server_exceptions=False)
    res = client.get("/api/health", headers={"x-forwarded-proto": "https"})
    hsts = res.headers.get("strict-transport-security", "")
    assert "max-age=31536000" in hsts
    assert "includeSubDomains" in hsts


def test_security_headers_present_on_login_page(client):
    """Security headers must appear on non-API routes too."""
    res = client.get("/login")
    assert res.headers.get("x-frame-options") == "DENY"
    assert res.headers.get("x-content-type-options") == "nosniff"
