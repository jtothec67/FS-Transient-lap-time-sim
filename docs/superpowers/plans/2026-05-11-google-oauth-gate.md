# Google OAuth Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Put every page and API route of the LGR Sim Workbench behind a "Sign in with Google" gate so a public deployment URL can only be used by people who have authenticated, while keeping the implementation minimal (no database, no user management UI, no monitoring).

**Architecture:** Use Authlib's Starlette OAuth client for the Google authorization-code flow, and Starlette's `SessionMiddleware` for a signed-cookie session. A `require_user` FastAPI dependency reads the session and 401s if absent. Every existing `/api/*` route except `/api/health` gets the dependency. The root `/` route redirects to `/login` when unauthenticated. There is no allowlist — any Google account that successfully completes the OAuth flow is granted access. All secrets come from environment variables so they can be injected via Fly.io secrets in production.

**Tech Stack:** Authlib (Starlette OAuth client), itsdangerous (session cookie signing — already a Starlette dep), FastAPI, pytest with `TestClient`. No database. No frontend framework change.

**Scope notes:**
- This plan does NOT touch the DeepSeek API key handling. That key remains a plaintext file at `config/deepseek_key`. With the auth gate in place, only signed-in users can hit `/api/chat`, but the key is still drainable by any logged-in user. A per-user or per-IP rate limit on `/api/chat` is out of scope for this plan.
- This plan assumes Fly.io as the host and assumes Phase 2-lite (Dockerfile, env-var-driven config, etc.) is already in place or will be handled separately. The plan only adds env vars; it does not write a Dockerfile.
- The frontend stays vanilla JS. The /login page is a static HTML file served by FastAPI.
- The existing 98-test suite must continue to pass; new auth tests use `dependency_overrides` so they don't need a real Google client.

---

## File Structure

**New files:**
- `src/app/auth.py` — OAuth client registration, session helpers, `require_user` dependency, and a route-factory function that returns the three auth routes (`/login`, `/auth/callback`, `/logout`)
- `src/app/static/login.html` — minimal sign-in landing page styled to match the existing app aesthetic
- `tests/test_auth.py` — TestClient-driven tests for the unauthenticated → 401, authenticated → 200, health-endpoint-open, and login-page-renders cases
- `docs/DEPLOYMENT.md` — short setup notes covering the Google Cloud OAuth credential creation and the Fly secret commands

**Modified files:**
- `pyproject.toml` — add `authlib>=1.3.0` and `itsdangerous>=2.2.0` to dependencies
- `src/app/web.py` — register `SessionMiddleware`, register auth routes, redirect-or-serve at `/`, attach `Depends(require_user)` to every `/api/*` endpoint except `/api/health`
- `src/app/static/app.js` — global fetch wrapper that redirects to `/login` on 401, header showing logged-in email and a logout button
- `src/app/static/index.html` — small header element to display email + logout button

---

## Environment variables

The implementation reads these via `os.environ`. They will be set as Fly secrets in production and exported locally for development.

| Variable | Required? | Example | Purpose |
|---|---|---|---|
| `GOOGLE_CLIENT_ID` | yes | `1234.apps.googleusercontent.com` | OAuth client id from Google Cloud Console |
| `GOOGLE_CLIENT_SECRET` | yes | `GOCSPX-...` | OAuth client secret |
| `SESSION_SECRET` | yes | 32+ random bytes hex | Signs the session cookie |
| `APP_BASE_URL` | yes | `http://localhost:8000` or `https://your-app.fly.dev` | Used to construct the OAuth redirect URI; must match the URI registered with Google |
| `COOKIE_SECURE` | optional, default `false` | `true` in prod | Forces `Secure` flag on the session cookie (HTTPS only) |

If `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `SESSION_SECRET`, or `APP_BASE_URL` is missing at app startup, the app raises `RuntimeError` immediately. This is intentional — silently allowing unauthenticated access in prod because someone forgot to set a secret is the failure mode we want to avoid.

---

## Task 1: Add dependencies

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add Authlib and itsdangerous to dependencies**

In `pyproject.toml`, in the `[project]` `dependencies` array, add two new entries (alphabetical order):

```toml
dependencies = [
    "authlib>=1.3.0",
    "cryptography>=44.0.0",
    "fastapi>=0.118.0",
    "httpx>=0.28.0",
    "itsdangerous>=2.2.0",
    "matplotlib>=3.10.8",
    "numpy>=2.4.2",
    "pandas>=3.0.0",
    "scipy>=1.17.0",
    "seaborn>=0.13.2",
    "uvicorn>=0.37.0",
]
```

- [ ] **Step 2: Install the new deps**

Run: `uv sync`

Expected: `authlib` and `itsdangerous` appear in `uv.lock`. No errors.

- [ ] **Step 3: Confirm the imports work**

Run: `uv run python -c "from authlib.integrations.starlette_client import OAuth; from starlette.middleware.sessions import SessionMiddleware; print('ok')"`

Expected: `ok`.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "deps: add authlib and itsdangerous for Google OAuth gate"
```

---

## Task 2: Create the auth module

**Files:**
- Create: `src/app/auth.py`
- Test: `tests/test_auth_unit.py` (unit tests for the module's pure helpers)

The module owns four responsibilities, in one file because they all change together:
1. Read required env vars and fail loudly if missing
2. Build a singleton Authlib `OAuth` instance configured for Google
3. Expose a `require_user` FastAPI dependency that returns the email from the session or raises 401
4. Build the three auth routes (`/login`, `/auth/callback`, `/logout`) on a given `FastAPI` app

- [ ] **Step 1: Write failing unit tests for the env-loading helper**

Write `tests/test_auth_unit.py`:

```python
import os

import pytest

from app.auth import AuthConfig, load_auth_config


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
```

- [ ] **Step 2: Run the tests to confirm they fail**

Run: `uv run pytest tests/test_auth_unit.py -v`

Expected: `ImportError` for `app.auth`.

- [ ] **Step 3: Implement the auth module**

Write `src/app/auth.py`:

```python
"""Google OAuth gate. One module owns env-loading, the Authlib client,
the FastAPI session dependency, and the route factory."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable

from authlib.integrations.starlette_client import OAuth, OAuthError
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse


_REQUIRED_ENV = ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "SESSION_SECRET", "APP_BASE_URL")


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
    email = request.session.get("email") if hasattr(request, "session") else None
    if not email:
        raise HTTPException(status_code=401, detail="Authentication required")
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
        request.session["email"] = userinfo["email"]
        return RedirectResponse(url="/", status_code=303)

    @app.post("/logout")
    def logout(request: Request) -> RedirectResponse:
        request.session.clear()
        return RedirectResponse(url="/login", status_code=303)
```

- [ ] **Step 4: Run the tests to confirm they pass**

Run: `uv run pytest tests/test_auth_unit.py -v`

Expected: all 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/app/auth.py tests/test_auth_unit.py
git commit -m "feat(auth): add auth module with Google OAuth client and require_user dependency"
```

---

## Task 3: Wire auth into the FastAPI app

**Files:**
- Modify: `src/app/web.py`

This is where the gate is actually installed. Every `/api/*` route except `/api/health` gets `Depends(require_user)`. The root `/` route redirects to `/login` if there is no session. `/api/health` stays open so Fly.io's TCP/HTTP health probes don't need an auth token.

- [ ] **Step 1: Refactor `src/app/web.py` to install the auth gate**

Replace the contents of `src/app/web.py` with:

```python
import os
os.environ.setdefault("MPLBACKEND", "Agg")

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.auth import build_oauth_client, load_auth_config, register_auth_routes, require_user
from app.paths import lessons_dir, static_dir
from app.schemas import LapRunRequest, LiftCoastRequest, SweepRequest, TyreVerifyRequest, ChatRequest, ChatResponse
from app.services.lap_service import get_config, get_parameters, metadata, run_lap
from app.services.lift_coast_service import run_lift_coast
from app.services.sweep_service import run_sweep
from app.services.tyre_service import run_tyre_verify
from app.services.chat_service import chat


def create_app() -> FastAPI:
    app = FastAPI(title="LGR Sim Workbench", version="0.1.0")

    auth_cfg = load_auth_config()
    oauth = build_oauth_client(auth_cfg)

    app.add_middleware(
        SessionMiddleware,
        secret_key=auth_cfg.session_secret,
        https_only=auth_cfg.cookie_secure,
        same_site="lax",
    )

    static_root = static_dir()
    lessons_root = lessons_dir()
    app.mount("/static", StaticFiles(directory=str(static_root)), name="static")
    app.mount("/lessons", StaticFiles(directory=str(lessons_root)), name="lessons")

    register_auth_routes(app, auth_cfg, oauth, static_root / "login.html")

    @app.get("/")
    def index(request: Request):
        if not request.session.get("email"):
            return RedirectResponse(url="/login", status_code=303)
        return FileResponse(static_root / "index.html")

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.get("/api/me")
    def me(email: str = Depends(require_user)) -> dict:
        return {"email": email}

    @app.get("/api/datasets")
    def list_datasets(email: str = Depends(require_user)) -> dict:
        from app.security.dataset_registry import (
            list_track_ids,
            list_tyre_lateral_ids,
            list_tyre_longitudinal_ids,
        )
        return {
            "tracks": list_track_ids(),
            "tyre_lateral": list_tyre_lateral_ids(),
            "tyre_longitudinal": list_tyre_longitudinal_ids(),
        }

    @app.get("/api/metadata")
    def get_metadata(email: str = Depends(require_user)) -> dict:
        return metadata()

    @app.get("/api/parameters")
    def get_parameters_endpoint(email: str = Depends(require_user)) -> dict:
        return get_parameters()

    @app.get("/api/config")
    def get_config_endpoint(email: str = Depends(require_user)) -> dict:
        cfg = get_config()
        return {
            "debug_mode": False,
            "full_telemetry_mode": bool(cfg.get("full_telemetry_mode", True)),
            "solver": {
                "use_rollover_speed_cap": bool(cfg.get("solver", {}).get("use_rollover_speed_cap", True)),
                "max_brake_decel_g": float(cfg.get("solver", {}).get("max_brake_decel_g", 2.0)),
            },
            "ambient_conditions": {
                "air_density": float(cfg.get("ambient_conditions", {}).get("air_density", 1.225)),
            },
        }

    @app.post("/api/lap/run")
    def run_lap_endpoint(req: LapRunRequest, email: str = Depends(require_user)) -> dict:
        return run_lap(parameters=req.parameters, overrides=req.overrides)

    @app.post("/api/tyre/verify")
    def tyre_verify_endpoint(req: TyreVerifyRequest, email: str = Depends(require_user)) -> dict:
        return run_tyre_verify(
            lat_dataset=req.lat_dataset,
            long_dataset=req.long_dataset,
            model_variant=req.model_variant,
            rmse_threshold_pct=req.rmse_threshold_pct,
            base_mu=req.base_mu,
        )

    @app.post("/api/sweep/run")
    def run_sweep_endpoint(req: SweepRequest, email: str = Depends(require_user)) -> dict:
        return run_sweep(
            param=req.param,
            values=req.values,
            steps=req.steps,
            parameters=req.parameters,
            overrides=req.overrides,
        )

    @app.post("/api/lift-coast/run")
    def run_lift_coast_endpoint(req: LiftCoastRequest, email: str = Depends(require_user)) -> dict:
        return run_lift_coast(
            power_limits_kw=req.power_limits_kw,
            energy_target_kwh=req.energy_target_kwh,
            dt=req.dt,
            parameter_overrides=req.parameter_overrides,
        )

    @app.post("/api/chat")
    def chat_endpoint(req: ChatRequest, email: str = Depends(require_user)) -> ChatResponse:
        try:
            return chat(question=req.question, history=req.history)
        except FileNotFoundError:
            raise HTTPException(status_code=503, detail="Chat is not configured.")
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=str(exc))

    return app
```

- [ ] **Step 2: Confirm the app fails to start without env vars**

Run: `uv run python -c "from app.web import create_app; create_app()"`

Expected: `RuntimeError: Missing required environment variables for auth: GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, SESSION_SECRET, APP_BASE_URL`

This is correct — the app refuses to boot without auth configured.

- [ ] **Step 3: Confirm the app starts with env vars set**

In PowerShell:
```powershell
$env:GOOGLE_CLIENT_ID="test"; $env:GOOGLE_CLIENT_SECRET="test"; $env:SESSION_SECRET="test"; $env:APP_BASE_URL="http://localhost:8000"
uv run python -c "from app.web import create_app; create_app(); print('ok')"
```

Expected: `ok`.

- [ ] **Step 4: Run the existing security smoke suite — it will FAIL until Task 5 adds test fixtures**

Run: `uv run pytest tests/test_security_smoke.py -v`

Expected: every test that hits a `/api/*` route returns 401 unauthenticated. Note this — Task 5 fixes the test fixture to inject a session, restoring green.

- [ ] **Step 5: Commit**

```bash
git add src/app/web.py
git commit -m "feat(auth): gate all /api/* routes behind Google OAuth session"
```

---

## Task 4: Login page

**Files:**
- Create: `src/app/static/login.html`

A minimal, branded sign-in page consistent with the project's existing aesthetic (Studio Ghibli / engineering doc — `#006B5C` primary, `#101215` dark text, no emoji, no gradients, no purple). One headline, one button, no marketing fluff.

- [ ] **Step 1: Write `src/app/static/login.html`**

Write `src/app/static/login.html`:

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>LGR Sim Workbench — Sign in</title>
<link rel="stylesheet" href="/static/styles.css">
<style>
  body.login-page {
    background: #F4F6F8;
    color: #101215;
    margin: 0;
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    font-family: ui-sans-serif, system-ui, sans-serif;
  }
  .login-card {
    background: #ffffff;
    border: 1px solid #A7AEB6;
    padding: 32px 36px;
    max-width: 360px;
    width: 100%;
  }
  .login-card h1 {
    font-size: 18px;
    margin: 0 0 8px 0;
    color: #101215;
  }
  .login-card p {
    font-size: 14px;
    color: #101215;
    margin: 0 0 24px 0;
    line-height: 1.5;
  }
  .login-button {
    display: inline-block;
    background: #006B5C;
    color: #ffffff;
    border: none;
    padding: 10px 16px;
    font-size: 14px;
    cursor: pointer;
    text-decoration: none;
    font-family: inherit;
  }
  .login-button:hover {
    background: #00574B;
  }
</style>
</head>
<body class="login-page">
  <div class="login-card">
    <h1>LGR Sim Workbench</h1>
    <p>Sign in with Google to access the simulator.</p>
    <a class="login-button" href="/auth/start">Sign in with Google</a>
  </div>
</body>
</html>
```

- [ ] **Step 2: Manually verify the page renders**

Set the four env vars in your shell, run `uv run python -m uvicorn app.web:create_app --factory --port 8000`, open `http://localhost:8000/login` in a browser. Confirm the page shows the headline, the sentence, and the green "Sign in with Google" button. Do NOT click the button yet — Task 7 covers the end-to-end Google flow once you have real OAuth credentials.

- [ ] **Step 3: Commit**

```bash
git add src/app/static/login.html
git commit -m "feat(auth): add login page"
```

---

## Task 5: Auth integration tests

**Files:**
- Create: `tests/test_auth.py`
- Modify: `tests/test_security_smoke.py` (use the new fixture)
- Modify: `tests/test_api_telemetry.py` (use the new fixture)
- Modify: `tests/test_api_parameters_config.py` (use the new fixture)

All existing API tests need a way to bypass the OAuth flow. We expose a shared `authed_client` pytest fixture that overrides the `require_user` dependency to return a fake email. The fixture also sets the four required env vars so `create_app()` doesn't `RuntimeError`.

- [ ] **Step 1: Write the test fixtures and auth integration tests**

Write `tests/test_auth.py`:

```python
"""End-to-end tests for the auth gate."""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="session", autouse=True)
def _set_auth_env(tmp_path_factory):
    import os
    os.environ.setdefault("GOOGLE_CLIENT_ID", "test-client-id")
    os.environ.setdefault("GOOGLE_CLIENT_SECRET", "test-client-secret")
    os.environ.setdefault("SESSION_SECRET", "x" * 32)
    os.environ.setdefault("APP_BASE_URL", "http://testserver")
    yield


@pytest.fixture
def unauthed_client():
    from app.web import create_app
    return TestClient(create_app())


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


def test_auth_start_redirects_to_google(unauthed_client):
    res = unauthed_client.get("/auth/start", follow_redirects=False)
    assert res.status_code in (302, 303, 307)
    assert "accounts.google.com" in res.headers.get("location", "")
```

- [ ] **Step 2: Update `tests/test_security_smoke.py` to use the authed fixture**

Edit `tests/test_security_smoke.py`. Replace the existing module-level `client` fixture with the authed version. Find this block near the top:

```python
@pytest.fixture(scope="module")
def client():
    return TestClient(create_app())
```

Replace it with:

```python
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
```

Note: `test_workspace_endpoint_is_gone` does not need to change. FastAPI returns 404 for routes that aren't registered, regardless of whether the rest of the app is auth-gated. Verify this is true by running the smoke suite after Step 3.

- [ ] **Step 3: Update `tests/test_api_telemetry.py` to use the authed fixture**

Find the existing `lap_result` fixture in `tests/test_api_telemetry.py`:

```python
@pytest.fixture(scope="module")
def lap_result():
    client = TestClient(create_app())
    res = client.post('/api/lap/run', json={})
    assert res.status_code == 200
    return res.json()
```

Replace it with:

```python
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
```

- [ ] **Step 4: Update `tests/test_api_parameters_config.py` the same way**

Open `tests/test_api_parameters_config.py`. It uses `TestClient(create_app())` in one or more fixtures or test functions. For each `TestClient(create_app())` call, replace with the authed variant:

```python
from app.auth import require_user
app = create_app()
app.dependency_overrides[require_user] = lambda: "tester@example.com"
client = TestClient(app)
```

Add the env-var autouse fixture at module level (copy from Step 3).

- [ ] **Step 5: Run the auth tests**

Run: `uv run pytest tests/test_auth.py -v`

Expected: all 9 tests PASS.

- [ ] **Step 6: Run the full suite**

Run: `uv run pytest tests/ -v`

Expected: every test PASSES, including the prior 98 tests from Phase 1 + the 9 new auth tests = ~107 tests.

If any pre-existing test still fails because it creates a `TestClient(create_app())` directly without the dependency override, find it and apply the same fix.

- [ ] **Step 7: Commit**

```bash
git add tests/
git commit -m "test(auth): add auth integration tests; update existing tests for authed client"
```

---

## Task 6: Frontend — handle 401, show email and logout

**Files:**
- Modify: `src/app/static/app.js` (add fetch wrapper, header rendering)
- Modify: `src/app/static/index.html` (add header element)

When the session expires or the cookie is missing, every API call returns 401. The frontend needs to detect this and redirect to `/login`. We also want the header to show the logged-in email and a logout button so users know who they're signed in as.

- [ ] **Step 1: Add a header element to `index.html`**

In `src/app/static/index.html`, find the existing top-of-page header (or the first element inside `<body>`). Add the following element as the very first child inside `<body>`. If a header element already exists, merge by adding the `.user-bar` div inside it:

```html
<div class="user-bar">
  <span class="user-bar-email" id="userBarEmail"></span>
  <button class="user-bar-logout" id="userBarLogout" type="button">Sign out</button>
</div>
```

Add corresponding CSS in `src/app/static/styles.css` (append to the end of the file):

```css
.user-bar {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 12px;
  padding: 8px 16px;
  background: #E8ECF0;
  border-bottom: 1px solid #A7AEB6;
  font-size: 13px;
  color: #101215;
}
.user-bar-email {
  font-family: ui-monospace, monospace;
}
.user-bar-logout {
  background: transparent;
  border: 1px solid #A7AEB6;
  padding: 4px 10px;
  font-size: 12px;
  cursor: pointer;
  color: #101215;
  font-family: inherit;
}
.user-bar-logout:hover {
  background: #ffffff;
}
```

- [ ] **Step 2: Add the fetch wrapper and user-bar initialization to `app.js`**

In `src/app/static/app.js`, add the following near the top of the file (after the existing top-level `const`/`let` declarations, before any function definitions that call `fetch`):

```javascript
async function apiFetch(input, init) {
  const res = await fetch(input, init);
  if (res.status === 401) {
    window.location.href = '/login';
    throw new Error('Not authenticated');
  }
  return res;
}

async function initUserBar() {
  try {
    const res = await apiFetch('/api/me');
    if (!res.ok) return;
    const body = await res.json();
    const emailEl = document.getElementById('userBarEmail');
    if (emailEl) emailEl.textContent = body.email || '';
  } catch (e) {
    // apiFetch already redirects on 401; nothing to do
  }
  const logoutBtn = document.getElementById('userBarLogout');
  if (logoutBtn) {
    logoutBtn.addEventListener('click', async () => {
      const form = document.createElement('form');
      form.method = 'POST';
      form.action = '/logout';
      document.body.appendChild(form);
      form.submit();
    });
  }
}
```

Replace every `fetch(` call in this file with `apiFetch(`. Search the file for `fetch(` to find each call site. There are typically 5-10 of these for the various `/api/...` endpoints. Each one becomes:

```javascript
// Before
const res = await fetch('/api/lap/run', { method: 'POST', ... });

// After
const res = await apiFetch('/api/lap/run', { method: 'POST', ... });
```

Finally, find the existing init function (the one called on `DOMContentLoaded` or at the end of the file) and add a call to `initUserBar()` at the start of it.

- [ ] **Step 3: Manually verify the frontend behaviour**

With the four env vars set and the app running locally:

1. Go to `http://localhost:8000/`. Expect: redirect to `/login`.
2. Open browser dev tools, set a cookie `session=test` (any value). Reload `/`. Expect: page loads with `/api/me` returning 401 → JS redirects back to `/login`.
3. (After Task 7 you'll be able to test the full flow with real Google credentials.)

- [ ] **Step 4: Commit**

```bash
git add src/app/static/app.js src/app/static/index.html src/app/static/styles.css
git commit -m "feat(auth): frontend redirects to /login on 401; show email + logout"
```

---

## Task 7: Deployment documentation

**Files:**
- Create: `docs/DEPLOYMENT.md`

A short, practical setup guide for Google Cloud Console + Fly secrets. Not a manual for Fly itself — assumes the engineer already has a Fly app set up (matches the user's stated context).

- [ ] **Step 1: Write `docs/DEPLOYMENT.md`**

Write `docs/DEPLOYMENT.md`:

```markdown
# Deployment Notes — Google OAuth Gate

These notes cover the auth-specific configuration. They assume your Fly.io app
already exists and that the rest of the deployment (Dockerfile, Procfile, etc.)
is wired up.

## Google Cloud setup

1. Go to https://console.cloud.google.com/apis/credentials
2. Create a new project if you don't have one
3. OAuth consent screen — choose "External", fill in app name, support email,
   and developer contact. You can leave it in Testing mode while you collect
   feedback (Google allows up to 100 test users without verification)
4. Credentials — Create credentials, "OAuth client ID", Application type "Web application"
5. Authorized redirect URIs — add BOTH:
   - `http://localhost:8000/auth/callback` (for local development)
   - `https://<your-fly-app>.fly.dev/auth/callback` (your production URL)
6. Save. Copy the Client ID and Client Secret.

## Environment variables

The app requires four environment variables to start. If any is missing,
`create_app()` raises `RuntimeError` at startup and Fly will mark the deploy
as failed.

| Variable | Local dev | Production |
|---|---|---|
| `GOOGLE_CLIENT_ID` | from Google Cloud Console | same |
| `GOOGLE_CLIENT_SECRET` | from Google Cloud Console | same |
| `SESSION_SECRET` | any 32+ char string | a freshly generated 32+ byte random hex |
| `APP_BASE_URL` | `http://localhost:8000` | `https://<your-fly-app>.fly.dev` |
| `COOKIE_SECURE` | `false` or unset | `true` |

Generate a fresh `SESSION_SECRET`:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

## Setting Fly secrets

From the repo root with `flyctl` installed:

```bash
flyctl secrets set \
  GOOGLE_CLIENT_ID="<paste here>" \
  GOOGLE_CLIENT_SECRET="<paste here>" \
  SESSION_SECRET="<paste 64-char hex>" \
  APP_BASE_URL="https://<your-fly-app>.fly.dev" \
  COOKIE_SECURE="true"
```

Fly will restart the app automatically once the secrets are saved.

## Local development

Create a `.env` file at the repo root (this file is gitignored — do not commit it).

```bash
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
SESSION_SECRET=any-string-at-least-32-chars-long
APP_BASE_URL=http://localhost:8000
```

Load it before running locally. In PowerShell:

```powershell
Get-Content .env | ForEach-Object {
  if ($_ -match '^\s*([^#=]+)=(.*)$') {
    [System.Environment]::SetEnvironmentVariable($matches[1].Trim(), $matches[2].Trim(), 'Process')
  }
}
uv run python -m uvicorn app.web:create_app --factory --port 8000
```

## Verifying the deploy

After deploying:

1. `curl https://<your-fly-app>.fly.dev/api/health` — should return `{"status":"ok"}`
   with no auth.
2. `curl -i https://<your-fly-app>.fly.dev/` — should return 303 redirect to `/login`.
3. `curl -i https://<your-fly-app>.fly.dev/api/datasets` — should return 401.
4. Visit `https://<your-fly-app>.fly.dev/login` in a browser, click "Sign in
   with Google", complete the flow, and confirm the main app loads.

## What this auth does NOT do

- No allowlist. Any Google account that completes the flow is granted access.
  If you want to restrict access to specific emails, you would add an allowlist
  check in `src/app/auth.py` `auth_callback` — that's deliberately out of scope
  here.
- No rate limiting. A signed-in user can still drain your DeepSeek API budget
  by spamming `/api/chat`. Consider adding `slowapi` or a per-session counter
  if cost is a concern.
- No session persistence. Sessions live in a signed cookie. Restarting the
  app does not invalidate existing sessions unless you rotate `SESSION_SECRET`.
- No CSRF protection beyond `SameSite=Lax`. Authlib generates and validates
  the OAuth state parameter, which is sufficient for the OAuth flow itself.
```

- [ ] **Step 2: Update `.gitignore` to ignore `.env`**

Open `.gitignore`. If `.env` is not already listed, add it on a new line. If it is already there, do nothing.

- [ ] **Step 3: Commit**

```bash
git add docs/DEPLOYMENT.md .gitignore
git commit -m "docs(auth): deployment notes for Google OAuth + Fly secrets"
```

---

## Task 8: End-to-end manual verification

This is a non-coding task. After all earlier tasks are done and committed, do a manual smoke test against a real Google OAuth client.

- [ ] **Step 1: Create the Google OAuth credentials**

Follow `docs/DEPLOYMENT.md` "Google Cloud setup" to create OAuth client ID + secret.

- [ ] **Step 2: Set local env vars**

Either create `.env` and load it, or export them inline.

- [ ] **Step 3: Run the app locally**

```powershell
uv run python -m uvicorn app.web:create_app --factory --port 8000
```

- [ ] **Step 4: Verify the full flow**

1. Browse to `http://localhost:8000/` — confirm it redirects to `/login`.
2. Click "Sign in with Google".
3. Choose a Google account (must be a test user if your consent screen is in Testing mode).
4. Confirm the browser lands back on `/` and the main app loads.
5. Confirm the user bar shows your email.
6. Click "Sign out". Confirm you're back at `/login`.
7. After signing out, manually visit `http://localhost:8000/api/datasets` — confirm 401.

- [ ] **Step 5: Deploy and verify in production**

```bash
flyctl secrets set ...   # see DEPLOYMENT.md
flyctl deploy
```

Then run the four verification curls from `DEPLOYMENT.md` "Verifying the deploy".

No commit for this task — it's verification only.

---

## Self-review checklist

After implementation, verify each item maps to a closed requirement:

- [ ] `/api/health` is open (no auth) → Task 3
- [ ] `/api/me` returns the email of the signed-in user → Task 3
- [ ] All other `/api/*` routes require auth → Task 3 (verified by Task 5 test)
- [ ] `/` redirects to `/login` when unauthenticated → Task 3
- [ ] `/login` renders a "Sign in with Google" page → Tasks 2 + 4
- [ ] `/auth/start` redirects to Google's OAuth consent screen → Task 2
- [ ] `/auth/callback` exchanges the code and sets `request.session["email"]` → Task 2
- [ ] `/logout` clears the session and redirects to `/login` → Task 2
- [ ] App fails to start if any required env var is missing → Task 2 (verified by Task 3 Step 2)
- [ ] Frontend redirects to `/login` on any 401 → Task 6
- [ ] User bar shows email and a sign-out button → Task 6
- [ ] Deployment instructions for Google Cloud + Fly secrets → Task 7

**Out of scope (intentional):**
- Email allowlist
- Rate limiting / abuse prevention
- Per-user state or audit logging
- Magic links / passwordless / non-Google providers
- CSRF tokens beyond what Authlib provides
- Session persistence across `SESSION_SECRET` rotation
