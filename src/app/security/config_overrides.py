"""Server-side reconstruction of the simulator config from a typed override payload.

The simulator's full config dict references multiple dataset files (powertrain CSV,
tyre data, track file). We do not let clients touch those paths -- we accept only a
small set of tunable scalars and an optional track ID, and we always anchor everything
else to the server's `config.json`."""
from __future__ import annotations

import copy

from pydantic import BaseModel, Field

from app.security.dataset_registry import get_track_path


class ConfigOverrides(BaseModel):
    """User-supplied tunables that may override the base config. No paths."""
    model_config = {"extra": "forbid"}

    track_id: str | None = Field(default=None, max_length=64)
    air_density: float | None = Field(default=None, ge=0.5, le=2.0)
    max_brake_decel_g: float | None = Field(default=None, ge=0.0, le=5.0)
    use_rollover_speed_cap: bool | None = None
    full_telemetry_mode: bool | None = None


def build_config(base_config: dict, overrides: ConfigOverrides) -> dict:
    """Return a fresh config dict combining `base_config` with `overrides`.

    Track file path is rewritten to the registry-resolved absolute path so the
    rest of the simulator code does not need to know about dataset IDs."""
    cfg = copy.deepcopy(base_config)

    # Always force debug_mode off -- it triggers plt.show() etc. on a headless server.
    cfg["debug_mode"] = False

    if overrides.track_id is not None:
        track_path = get_track_path(overrides.track_id)
    else:
        cfg.setdefault("track", {})
        track_path = _resolve_default_track(cfg["track"].get("file_path"))
    cfg.setdefault("track", {})["file_path"] = str(track_path)

    if overrides.air_density is not None:
        cfg.setdefault("ambient_conditions", {})["air_density"] = overrides.air_density

    if overrides.max_brake_decel_g is not None:
        cfg.setdefault("solver", {})["max_brake_decel_g"] = overrides.max_brake_decel_g

    if overrides.use_rollover_speed_cap is not None:
        cfg.setdefault("solver", {})["use_rollover_speed_cap"] = overrides.use_rollover_speed_cap

    if overrides.full_telemetry_mode is not None:
        cfg["full_telemetry_mode"] = overrides.full_telemetry_mode

    return cfg


def _resolve_default_track(rel_path: str | None) -> str:
    """The base config holds a relative track path. Resolve it via the same
    safe-path machinery without trusting any user input."""
    from app.paths import resolve_repo_path
    if not rel_path:
        return str(get_track_path("FSUK"))
    return str(resolve_repo_path(rel_path))
