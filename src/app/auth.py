"""Google OAuth gate. One module owns env-loading, the Authlib client,
the FastAPI session dependency, and the route factory."""
from __future__ import annotations

import os
from dataclasses import dataclass

from authlib.integrations.starlette_client import OAuth, OAuthError
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse


_REQUIRED_ENV = ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "SESSION_SECRET", "APP_BASE_URL")
_LOCAL_BASE_PREFIXES = ("http://localhost", "http://127.0.0.1")


def _load_allowlist() -> tuple[frozenset[str], frozenset[str]]:
    """Return (allowed_emails, allowed_domains) from env vars.

    If both sets are empty the gate is open to any verified Google email.
    Emails are stored lowercase for case-insensitive comparison.
    """
    raw_emails = os.environ.get("ALLOWED_EMAILS", "").strip()
    raw_domains = os.environ.get("ALLOWED_EMAIL_DOMAINS", "").strip()

    emails: frozenset[str] = frozenset(
        e.strip().lower() for e in raw_emails.split(",") if e.strip()
    )
    domains: frozenset[str] = frozenset(
        d.strip().lower() for d in raw_domains.split(",") if d.strip()
    )
    return emails, domains


def _check_allowlist(email: str) -> bool:
    """Return True if *email* passes the configured allowlist.

    Returns True unconditionally when no allowlist env vars are set.
    """
    allowed_emails, allowed_domains = _load_allowlist()
    if not allowed_emails and not allowed_domains:
        return True
    email_lower = email.lower()
    if email_lower in allowed_emails:
        return True
    domain = email_lower.split("@", 1)[-1] if "@" in email_lower else ""
    if domain and domain in allowed_domains:
        return True
    return False


@dataclass(frozen=True)
class AuthConfig:
    google_client_id: str
    google_client_secret: str
    session_secret: str
    app_base_url: str
    cookie_secure: bool

    @property
    def redirect_uri(self) -> str:
        return f"{self.app_base_url}/auth/callback"


def load_auth_config() -> AuthConfig:
    """Read the required env vars or fail loudly. Strips a trailing slash from APP_BASE_URL."""
    bypass_email = local_auth_bypass_email()
    if bypass_email:
        base = os.environ.get("APP_BASE_URL", "http://localhost:3000").rstrip("/")
        session_secret = os.environ.get("SESSION_SECRET", "local-dev-session-secret-change-me")
        return AuthConfig(
            google_client_id=os.environ.get("GOOGLE_CLIENT_ID", "local-dev-client-id"),
            google_client_secret=os.environ.get("GOOGLE_CLIENT_SECRET", "local-dev-client-secret"),
            session_secret=session_secret,
            app_base_url=base,
            cookie_secure=False,
        )

    missing = [v for v in _REQUIRED_ENV if not os.environ.get(v)]
    if missing:
        raise RuntimeError(
            f"Missing required environment variables for auth: {', '.join(missing)}"
        )
    base = os.environ["APP_BASE_URL"].rstrip("/")
    cookie_secure = os.environ.get("COOKIE_SECURE", "false").lower() in ("1", "true", "yes")
    return AuthConfig(
        google_client_id=os.environ["GOOGLE_CLIENT_ID"],
        google_client_secret=os.environ["GOOGLE_CLIENT_SECRET"],
        session_secret=os.environ["SESSION_SECRET"],
        app_base_url=base,
        cookie_secure=cookie_secure,
    )


def local_auth_bypass_email() -> str:
    """Return the local Docker/dev bypass user, but only for localhost base URLs."""
    email = os.environ.get("LOCAL_AUTH_BYPASS_EMAIL", "").strip()
    if not email:
        return ""
    base = os.environ.get("APP_BASE_URL", "http://localhost:3000").rstrip("/")
    if not base.startswith(_LOCAL_BASE_PREFIXES):
        raise RuntimeError("LOCAL_AUTH_BYPASS_EMAIL can only be used with a localhost APP_BASE_URL")
    return email


def build_oauth_client(cfg: AuthConfig) -> OAuth:
    oauth = OAuth()
    oauth.register(
        name="google",
        client_id=cfg.google_client_id,
        client_secret=cfg.google_client_secret,
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )
    return oauth


def require_user(request: Request) -> str:
    """FastAPI dependency. Returns the user's email if signed in, else 401."""
    bypass_email = local_auth_bypass_email()
    if bypass_email:
        return bypass_email

    email = request.session.get("email") if hasattr(request, "session") else None
    if not email:
        raise HTTPException(status_code=401, detail="Authentication required")
    if not _check_allowlist(email):
        raise HTTPException(status_code=403, detail="Your account is not authorised to access this application.")
    return email


def register_auth_routes(app: FastAPI, cfg: AuthConfig, oauth: OAuth, login_html_path) -> None:
    """Attach /login, /auth/callback, /logout to the given app."""

    @app.get("/login")
    def login_page() -> FileResponse:
        return FileResponse(str(login_html_path))

    @app.get("/auth/start")
    async def auth_start(request: Request):
        return await oauth.google.authorize_redirect(request, cfg.redirect_uri)

    @app.get("/auth/callback")
    async def auth_callback(request: Request):
        try:
            token = await oauth.google.authorize_access_token(request)
        except OAuthError as exc:
            raise HTTPException(status_code=400, detail=f"OAuth error: {exc.error}")
        userinfo = token.get("userinfo")
        if not userinfo or not userinfo.get("email"):
            raise HTTPException(status_code=400, detail="Google did not return an email")
        if not userinfo.get("email_verified", False):
            raise HTTPException(status_code=403, detail="Email is not verified by Google")
        email = userinfo["email"]
        if not _check_allowlist(email):
            raise HTTPException(status_code=403, detail="Your account is not authorised to access this application.")
        request.session["email"] = email
        return RedirectResponse(url="/", status_code=303)

    @app.post("/logout")
    def logout(request: Request) -> RedirectResponse:
        request.session.clear()
        return RedirectResponse(url="/login", status_code=303)
