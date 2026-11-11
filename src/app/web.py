import logging
import os
os.environ.setdefault("MPLBACKEND", "Agg")

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import Response

from app.auth import build_oauth_client, load_auth_config, local_auth_bypass_email, register_auth_routes, require_user
from app.paths import lessons_dir, static_dir
from app.schemas import LapRunRequest, LiftCoastRequest, SweepRequest, TyreVerifyRequest, ChatRequest, ChatResponse
from app.services.lap_service import get_config, get_parameters, metadata, run_lap
from app.services.lift_coast_service import run_lift_coast
from app.services.sweep_service import run_sweep
from app.services.tyre_service import run_tyre_verify
from app.services.chat_service import chat

_log = logging.getLogger(__name__)

# Set RATE_LIMIT_DISABLED=1 in test environments to prevent rate-limit state
# from accumulating across tests in a single pytest session.
_rate_limits_enabled = os.environ.get("RATE_LIMIT_DISABLED", "").lower() not in ("1", "true", "yes")
limiter = Limiter(key_func=get_remote_address, enabled=_rate_limits_enabled)


def _basename(path: str) -> str:
    if not path:
        return ""
    return path.replace("\\", "/").rsplit("/", 1)[-1]


async def _rate_limit_handler(request: Request, exc: RateLimitExceeded) -> Response:
    retry_after = str(getattr(exc, "retry_after", 60))
    return Response(
        content='{"detail":"Rate limit exceeded. Please slow down."}',
        status_code=429,
        media_type="application/json",
        headers={"Retry-After": retry_after},
    )


class SecurityHeadersMiddleware:
    """Attach security headers to every response.

    HSTS is only set when the request arrives over HTTPS, either directly or
    via the X-Forwarded-Proto header that Fly.io sets.
    """

    _CSP = (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "font-src 'self' data:;"
    )

    def __init__(self, app) -> None:
        self._app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        request = Request(scope, receive)
        forwarded_proto = request.headers.get("x-forwarded-proto", "")
        scheme = forwarded_proto or request.url.scheme
        is_https = scheme == "https"

        async def send_with_headers(message) -> None:
            if message["type"] == "http.response.start":
                headers = dict(message.get("headers", []))
                headers[b"x-frame-options"] = b"DENY"
                headers[b"x-content-type-options"] = b"nosniff"
                headers[b"referrer-policy"] = b"same-origin"
                headers[b"permissions-policy"] = b"camera=(), microphone=(), geolocation=()"
                headers[b"content-security-policy"] = self._CSP.encode()
                if is_https:
                    headers[b"strict-transport-security"] = b"max-age=31536000; includeSubDomains"
                message = {**message, "headers": list(headers.items())}
            await send(message)

        await self._app(scope, receive, send_with_headers)


def create_app() -> FastAPI:
    app = FastAPI(title="LGR Sim Workbench", version="0.1.0")

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_handler)

    auth_cfg = load_auth_config()
    oauth = build_oauth_client(auth_cfg)

    # Security headers on every response
    app.add_middleware(SecurityHeadersMiddleware)
    # Rate limiting via slowapi
    app.add_middleware(SlowAPIMiddleware)
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
        if not request.session.get("email") and not local_auth_bypass_email():
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
        from app.security.dataset_registry import (
            get_track_label,
            get_tyre_lateral_label,
            get_tyre_longitudinal_label,
            lookup_powertrain_label_by_path,
            lookup_track_id_by_path,
            lookup_tyre_lateral_id_by_path,
            lookup_tyre_longitudinal_id_by_path,
        )
        cfg = get_config()
        max_brake_decel_g = cfg.get("solver", {}).get("max_brake_decel_g")

        powertrain_path = cfg.get("powertrain", {}).get("powertrain", "")
        track_path      = cfg.get("track", {}).get("file_path", "")
        tyre_lat_path   = cfg.get("tyre_model", {}).get("file_path_lateral", "")
        tyre_long_path  = cfg.get("tyre_model", {}).get("file_path_longit",  "")

        track_id    = lookup_track_id_by_path(track_path)
        tyre_lat_id = lookup_tyre_lateral_id_by_path(tyre_lat_path)
        tyre_long_id = lookup_tyre_longitudinal_id_by_path(tyre_long_path)

        powertrain_label = lookup_powertrain_label_by_path(powertrain_path) or _basename(powertrain_path)
        track_label    = get_track_label(track_id) if track_id else _basename(track_path)
        tyre_lat_label = get_tyre_lateral_label(tyre_lat_id) if tyre_lat_id else _basename(tyre_lat_path)
        tyre_long_label = get_tyre_longitudinal_label(tyre_long_id) if tyre_long_id else _basename(tyre_long_path)

        return {
            "full_telemetry_mode": bool(cfg.get("full_telemetry_mode", True)),
            "solver": {
                "use_rollover_speed_cap": bool(cfg.get("solver", {}).get("use_rollover_speed_cap", True)),
                "max_brake_decel_g": None if max_brake_decel_g is None else float(max_brake_decel_g),
            },
            "ambient_conditions": {
                "air_density": float(cfg.get("ambient_conditions", {}).get("air_density", 1.225)),
            },
            "datasets": {
                "powertrain":         {"label": powertrain_label},
                "track":              {"id": track_id,    "label": track_label},
                "tyre_lateral":       {"id": tyre_lat_id, "label": tyre_lat_label},
                "tyre_longitudinal":  {"id": tyre_long_id, "label": tyre_long_label},
            },
        }

    @app.post("/api/lap/run")
    @limiter.limit("10/minute")
    def run_lap_endpoint(request: Request, req: LapRunRequest, email: str = Depends(require_user)) -> dict:
        return run_lap(parameters=req.parameters, overrides=req.overrides)

    @app.get("/api/track/datasets")
    def list_track_datasets(email: str = Depends(require_user)) -> list[dict[str, str]]:
        from app.security.dataset_registry import list_tracks
        return list_tracks()

    @app.get("/api/tyre/datasets")
    def list_tyre_datasets(email: str = Depends(require_user)) -> dict:
        from app.security.dataset_registry import list_tyre_lateral, list_tyre_longitudinal
        return {
            "lateral": list_tyre_lateral(),
            "longitudinal": list_tyre_longitudinal(),
        }

    @app.post("/api/tyre/verify")
    @limiter.limit("10/minute")
    def tyre_verify_endpoint(request: Request, req: TyreVerifyRequest, email: str = Depends(require_user)) -> dict:
        return run_tyre_verify(
            lat_dataset=req.lat_dataset,
            long_dataset=req.long_dataset,
            model_variant=req.model_variant,
            rmse_threshold_pct=req.rmse_threshold_pct,
            base_mu=req.base_mu,
            mu_multiplier=req.mu_multiplier,
        )

    @app.post("/api/sweep/run")
    @limiter.limit("3/minute")
    def run_sweep_endpoint(request: Request, req: SweepRequest, email: str = Depends(require_user)) -> dict:
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
    @limiter.limit("20/minute")
    def chat_endpoint(request: Request, req: ChatRequest, email: str = Depends(require_user)) -> ChatResponse:
        try:
            return chat(question=req.question, history=req.history)
        except FileNotFoundError:
            raise HTTPException(status_code=503, detail="Chat is not configured.")
        except httpx.HTTPError as exc:
            _log.warning("DeepSeek request failed: %s", exc)
            raise HTTPException(status_code=502, detail="The assistant is temporarily unavailable.")

    return app
