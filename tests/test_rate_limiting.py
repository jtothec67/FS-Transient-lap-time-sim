"""Tests for per-IP rate limiting on compute endpoints.

Each test patches the module-level limiter with a fresh instance so
counts from other tests (including other test files) cannot bleed in.
"""
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _set_auth_env(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "test-client-secret")
    monkeypatch.setenv("SESSION_SECRET", "x" * 32)
    monkeypatch.setenv("APP_BASE_URL", "http://testserver")


@pytest.fixture
def rate_limit_client():
    """Provide a TestClient with:
    - a fresh Limiter (zero counts)
    - run_lap mocked to return immediately
    - auth bypassed
    """
    from slowapi import Limiter
    from slowapi.util import get_remote_address
    from slowapi.errors import RateLimitExceeded
    from slowapi.middleware import SlowAPIMiddleware
    from starlette.responses import Response
    import app.web as web_module
    from app.web import create_app, _rate_limit_handler
    from app.auth import require_user

    # Force enabled=True so the fresh limiter enforces limits regardless of the
    # RATE_LIMIT_DISABLED env var that conftest sets for the rest of the test suite.
    fresh_limiter = Limiter(key_func=get_remote_address, enabled=True)

    with (
        patch.object(web_module, "limiter", fresh_limiter),
        patch("app.web.run_lap", return_value={"lap_time": 42.0}),
    ):
        app = create_app()
        app.dependency_overrides[require_user] = lambda: "tester@example.com"
        yield TestClient(app, raise_server_exceptions=False)


def test_lap_run_rate_limit_11th_request_returns_429(rate_limit_client):
    """The 11th request to /api/lap/run within a window must return 429."""
    # First 10 requests must not be rate-limited
    for i in range(10):
        res = rate_limit_client.post("/api/lap/run", json={})
        assert res.status_code != 429, f"Request {i + 1} was rate-limited unexpectedly"

    # The 11th request must be rate-limited
    res = rate_limit_client.post("/api/lap/run", json={})
    assert res.status_code == 429
    assert "Retry-After" in res.headers


def test_rate_limit_response_has_retry_after_header(rate_limit_client):
    """429 responses from rate limiting include a Retry-After header."""
    for _ in range(10):
        rate_limit_client.post("/api/lap/run", json={})
    res = rate_limit_client.post("/api/lap/run", json={})
    assert res.status_code == 429
    assert "Retry-After" in res.headers


def test_rate_limit_response_body_has_detail(rate_limit_client):
    """429 response body includes a human-readable detail field."""
    for _ in range(10):
        rate_limit_client.post("/api/lap/run", json={})
    res = rate_limit_client.post("/api/lap/run", json={})
    assert res.status_code == 429
    body = res.json()
    assert "detail" in body
    assert "rate" in body["detail"].lower() or "slow" in body["detail"].lower()
