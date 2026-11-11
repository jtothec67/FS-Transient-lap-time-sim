"""Tests for email/domain allowlist in auth module."""
import pytest


@pytest.fixture(autouse=True)
def _clear_auth_env(monkeypatch):
    monkeypatch.delenv("ALLOWED_EMAILS", raising=False)
    monkeypatch.delenv("ALLOWED_EMAIL_DOMAINS", raising=False)
    monkeypatch.delenv("LOCAL_AUTH_BYPASS_EMAIL", raising=False)


def test_no_env_vars_any_email_passes():
    from app.auth import _check_allowlist
    assert _check_allowlist("anyone@anywhere.com") is True
    assert _check_allowlist("random@gmail.com") is True


def test_allowed_emails_only_exact_matches_pass(monkeypatch):
    monkeypatch.setenv("ALLOWED_EMAILS", "alice@x.com,bob@y.com")
    from app.auth import _check_allowlist
    assert _check_allowlist("alice@x.com") is True
    assert _check_allowlist("bob@y.com") is True
    assert _check_allowlist("charlie@x.com") is False
    assert _check_allowlist("alice@y.com") is False


def test_allowed_emails_case_insensitive(monkeypatch):
    monkeypatch.setenv("ALLOWED_EMAILS", "Alice@X.com")
    from app.auth import _check_allowlist
    assert _check_allowlist("alice@x.com") is True
    assert _check_allowlist("ALICE@X.COM") is True


def test_allowed_email_domains_any_matching_domain_passes(monkeypatch):
    monkeypatch.setenv("ALLOWED_EMAIL_DOMAINS", "mycompany.com")
    from app.auth import _check_allowlist
    assert _check_allowlist("engineer@mycompany.com") is True
    assert _check_allowlist("ceo@mycompany.com") is True
    assert _check_allowlist("engineer@other.com") is False


def test_allowed_email_domains_case_insensitive(monkeypatch):
    monkeypatch.setenv("ALLOWED_EMAIL_DOMAINS", "MyCompany.COM")
    from app.auth import _check_allowlist
    assert _check_allowlist("user@mycompany.com") is True


def test_both_env_vars_set_email_wins_over_domain(monkeypatch):
    monkeypatch.setenv("ALLOWED_EMAILS", "special@other.com")
    monkeypatch.setenv("ALLOWED_EMAIL_DOMAINS", "mycompany.com")
    from app.auth import _check_allowlist
    assert _check_allowlist("special@other.com") is True
    assert _check_allowlist("user@mycompany.com") is True
    assert _check_allowlist("other@other.com") is False


def test_require_user_rejects_unlisted_email(monkeypatch):
    """require_user raises 403 when the session email is not in the allowlist."""
    monkeypatch.setenv("ALLOWED_EMAILS", "allowed@x.com")
    from app.auth import _check_allowlist
    from fastapi import HTTPException
    from unittest.mock import MagicMock

    # Verify _check_allowlist returns False for unlisted email
    assert _check_allowlist("notallowed@x.com") is False

    # Simulate the full require_user code path with a faked session
    request = MagicMock()
    request.session = {"email": "notallowed@x.com"}

    # Temporarily unset LOCAL_AUTH_BYPASS_EMAIL so bypass doesn't fire
    monkeypatch.delenv("LOCAL_AUTH_BYPASS_EMAIL", raising=False)

    from app.auth import require_user
    with pytest.raises(HTTPException) as exc_info:
        require_user(request)
    assert exc_info.value.status_code == 403


def test_bypass_mode_ignores_allowlist(monkeypatch):
    """LOCAL_AUTH_BYPASS_EMAIL should bypass the allowlist check."""
    monkeypatch.setenv("ALLOWED_EMAILS", "alice@x.com")
    monkeypatch.setenv("LOCAL_AUTH_BYPASS_EMAIL", "dev@local.test")
    monkeypatch.setenv("APP_BASE_URL", "http://localhost:3000")
    from app.auth import require_user
    # require_user returns bypass email before any allowlist check
    from unittest.mock import MagicMock
    request = MagicMock()
    result = require_user(request)
    assert result == "dev@local.test"
