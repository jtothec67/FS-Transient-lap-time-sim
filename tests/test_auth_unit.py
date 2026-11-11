import os

import pytest

from app.auth import AuthConfig, load_auth_config, local_auth_bypass_email


@pytest.fixture(autouse=True)
def _clear_bypass_env(monkeypatch):
    monkeypatch.delenv("LOCAL_AUTH_BYPASS_EMAIL", raising=False)


def test_load_auth_config_returns_values_from_env(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "cid")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "csec")
    monkeypatch.setenv("SESSION_SECRET", "ssec")
    monkeypatch.setenv("APP_BASE_URL", "http://localhost:8000")
    monkeypatch.delenv("COOKIE_SECURE", raising=False)
    cfg = load_auth_config()
    assert cfg.google_client_id == "cid"
    assert cfg.google_client_secret == "csec"
    assert cfg.session_secret == "ssec"
    assert cfg.app_base_url == "http://localhost:8000"
    assert cfg.cookie_secure is False


def test_load_auth_config_respects_cookie_secure_true(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "cid")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "csec")
    monkeypatch.setenv("SESSION_SECRET", "ssec")
    monkeypatch.setenv("APP_BASE_URL", "https://x.fly.dev")
    monkeypatch.setenv("COOKIE_SECURE", "true")
    cfg = load_auth_config()
    assert cfg.cookie_secure is True


def test_load_auth_config_raises_if_any_required_var_missing(monkeypatch):
    for missing in ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "SESSION_SECRET", "APP_BASE_URL"):
        monkeypatch.setenv("GOOGLE_CLIENT_ID", "cid")
        monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "csec")
        monkeypatch.setenv("SESSION_SECRET", "ssec")
        monkeypatch.setenv("APP_BASE_URL", "http://localhost:8000")
        monkeypatch.delenv(missing)
        with pytest.raises(RuntimeError, match=missing):
            load_auth_config()


def test_load_auth_config_strips_trailing_slash_from_base_url(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "cid")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "csec")
    monkeypatch.setenv("SESSION_SECRET", "ssec")
    monkeypatch.setenv("APP_BASE_URL", "http://localhost:8000/")
    cfg = load_auth_config()
    assert cfg.app_base_url == "http://localhost:8000"


def test_auth_config_redirect_uri_is_callback_under_base_url(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "cid")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "csec")
    monkeypatch.setenv("SESSION_SECRET", "ssec")
    monkeypatch.setenv("APP_BASE_URL", "https://x.fly.dev")
    cfg = load_auth_config()
    assert cfg.redirect_uri == "https://x.fly.dev/auth/callback"


def test_bypass_unset_returns_empty(monkeypatch):
    monkeypatch.setenv("APP_BASE_URL", "http://localhost:3000")
    assert local_auth_bypass_email() == ""


def test_bypass_returns_email_on_localhost(monkeypatch):
    monkeypatch.setenv("LOCAL_AUTH_BYPASS_EMAIL", "dev@example.com")
    monkeypatch.setenv("APP_BASE_URL", "http://localhost:3000")
    assert local_auth_bypass_email() == "dev@example.com"


def test_bypass_returns_email_on_127_0_0_1(monkeypatch):
    monkeypatch.setenv("LOCAL_AUTH_BYPASS_EMAIL", "dev@example.com")
    monkeypatch.setenv("APP_BASE_URL", "http://127.0.0.1:3011")
    assert local_auth_bypass_email() == "dev@example.com"


def test_bypass_refuses_on_non_localhost_base_url(monkeypatch):
    monkeypatch.setenv("LOCAL_AUTH_BYPASS_EMAIL", "dev@example.com")
    monkeypatch.setenv("APP_BASE_URL", "https://lgr-simulator.fly.dev")
    with pytest.raises(RuntimeError, match="localhost"):
        local_auth_bypass_email()


def test_bypass_active_load_auth_config_does_not_require_google_env(monkeypatch):
    monkeypatch.setenv("LOCAL_AUTH_BYPASS_EMAIL", "dev@example.com")
    monkeypatch.setenv("APP_BASE_URL", "http://localhost:3000")
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.delenv("GOOGLE_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("SESSION_SECRET", raising=False)
    cfg = load_auth_config()
    assert cfg.app_base_url == "http://localhost:3000"
    assert cfg.cookie_secure is False
