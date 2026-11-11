# Phase 1: Public Launch Security Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the path-traversal, arbitrary-attribute-write, DoS, and info-leak vulnerabilities that the app inherited from its "trusted local user" assumption, so it is safe to expose to the public internet on Fly.io.

**Architecture:** Replace user-supplied file-path strings with short dataset IDs resolved against a server-side allowlist. Stop accepting an arbitrary `config: dict[str, Any]` from clients — accept a slim, typed override payload and reconstruct the simulator config server-side from `config.json` plus those allowlisted fields. Lock down vehicle-parameter overrides to an explicit allowlist. Bound list inputs. Remove endpoints and response fields that leak the server's filesystem layout. Force matplotlib's `Agg` backend so headless deploys do not crash.

**Tech Stack:** Python 3.12+, FastAPI, Pydantic v2, pytest, FastAPI `TestClient`. No new runtime dependencies are introduced.

**Scope notes:**
- This plan covers Phase 1 only (security hardening). Phase 2 (Fly.io packaging, env-var config, structured logging, Dockerfile) and Phase 3 (auth, rate limits, job queue) are separate plans.
- The frontend (`src/app/static/app.js`) must be updated alongside any request-shape change made here. Each task that changes a schema includes the corresponding `app.js` update.
- Existing tests under `tests/` use `pytest` with `fastapi.testclient.TestClient`. New tests in this plan follow the same pattern.

---

## File Structure

**New files:**
- `src/app/security/__init__.py` — empty package marker
- `src/app/security/dataset_registry.py` — allowlist of permitted track and tyre dataset short IDs, mapping each to a concrete filesystem path under `datasets/`
- `src/app/security/vehicle_params.py` — allowlist of vehicle-parameter attribute names that may be overridden via the API
- `src/app/security/config_overrides.py` — pure-function builder that takes the base `config.json` and a typed `ConfigOverrides` payload and returns the final simulator config; never reads paths from user input
- `tests/test_security_dataset_registry.py` — unit tests for the registry
- `tests/test_security_vehicle_params.py` — unit tests for the param allowlist
- `tests/test_security_config_overrides.py` — unit tests for the overrides builder
- `tests/test_security_smoke.py` — adversarial end-to-end tests against the live FastAPI app exercising every attack vector this plan closes

**Modified files:**
- `src/app/schemas.py` — replace `dict[str, Any]` payloads with strict typed models, add `Literal` enums for dataset IDs, add `max_length` on lists
- `src/app/web.py` — remove `/api/workspace`, sanitize `/api/config` and `/api/parameters` responses, set `MPLBACKEND=Agg` at module import
- `src/app/services/lap_service.py` — accept the new typed request, route through `config_overrides.build_config`, strip absolute paths from response
- `src/app/services/sweep_service.py` — same as lap, plus use `vehicle_params.canonical_or_reject`
- `src/app/services/tyre_service.py` — accept dataset short IDs instead of paths
- `src/app/services/lift_coast_service.py` — use `vehicle_params.canonical_or_reject` for the overrides loop
- `src/app/paths.py` — make `resolve_repo_path` reject absolute paths and `..` segments
- `src/app/static/app.js` — update fetch payloads to match new schemas

---

## Task 1: Dataset registry module

**Files:**
- Create: `src/app/security/__init__.py`
- Create: `src/app/security/dataset_registry.py`
- Test: `tests/test_security_dataset_registry.py`

The registry maps short IDs (e.g., `"FSUK"`) to concrete paths under `datasets/`. Callers never see raw user input; they look up by ID. Unknown IDs raise `ValueError`.

- [ ] **Step 1: Create the security package marker**

Write `src/app/security/__init__.py` as an empty file.

```python
```

- [ ] **Step 2: Write failing tests for the registry**

Write `tests/test_security_dataset_registry.py`:

```python
import pytest

from app.security.dataset_registry import (
    get_track_path,
    get_tyre_lateral_path,
    get_tyre_longitudinal_path,
    list_track_ids,
    list_tyre_lateral_ids,
    list_tyre_longitudinal_ids,
)


def test_get_track_path_known_id_returns_existing_file():
    path = get_track_path("FSUK")
    assert path.exists()
    assert path.name == "FSUK.txt"


def test_get_track_path_unknown_id_raises():
    with pytest.raises(ValueError, match="Unknown track id"):
        get_track_path("not_a_real_track")


def test_get_track_path_rejects_traversal_attempts():
    for hostile in ["../etc/passwd", "..\\..\\Windows", "/etc/passwd", "C:\\Windows", ""]:
        with pytest.raises(ValueError):
            get_track_path(hostile)


def test_list_track_ids_includes_seeded_tracks():
    ids = list_track_ids()
    assert "FSUK" in ids
    assert "SkidpadF26" in ids
    assert "StraightLineTrack" in ids


def test_get_tyre_lateral_path_known_id_returns_existing_file():
    path = get_tyre_lateral_path("round_8_12psi")
    assert path.exists()


def test_get_tyre_longitudinal_path_known_id_returns_existing_file():
    path = get_tyre_longitudinal_path("round_6_12psi")
    assert path.exists()


def test_tyre_ids_reject_unknown():
    with pytest.raises(ValueError):
        get_tyre_lateral_path("nope")
    with pytest.raises(ValueError):
        get_tyre_longitudinal_path("nope")


def test_lists_are_non_empty():
    assert list_tyre_lateral_ids()
    assert list_tyre_longitudinal_ids()
```

- [ ] **Step 3: Run the tests to confirm they fail**

Run: `uv run pytest tests/test_security_dataset_registry.py -v`

Expected: ImportError / ModuleNotFoundError for `app.security.dataset_registry`.

- [ ] **Step 4: Implement the registry**

Write `src/app/security/dataset_registry.py`:

```python
"""Allowlist of permitted dataset files. The web layer accepts short IDs only;
the IDs map to concrete paths beneath `datasets/`. Anything else is rejected."""
from __future__ import annotations

from pathlib import Path

from app.paths import repo_root

_TRACKS: dict[str, str] = {
    "FSUK": "datasets/tracks/FSUK.txt",
    "SkidpadF26": "datasets/tracks/SkidpadF26.txt",
    "StraightLineTrack": "datasets/tracks/StraightLineTrack.txt",
}

_TYRE_LATERAL: dict[str, str] = {
    "round_8_12psi": "datasets/vehicle/tyre_data/round_8_12_psi_lateral_load_tyredata_parsed.csv",
}

_TYRE_LONGITUDINAL: dict[str, str] = {
    "round_6_12psi": "datasets/vehicle/tyre_data/round_6_12_psi_longit_load_tyredata_parsed.csv",
}


def _lookup(table: dict[str, str], dataset_id: str, kind: str) -> Path:
    if not isinstance(dataset_id, str) or not dataset_id:
        raise ValueError(f"{kind} id must be a non-empty string")
    if dataset_id not in table:
        raise ValueError(f"Unknown {kind} id: {dataset_id!r}")
    candidate = repo_root() / table[dataset_id]
    resolved = candidate.resolve()
    root = repo_root().resolve()
    if root not in resolved.parents and resolved != root:
        raise ValueError(f"Resolved {kind} path escapes repo root")
    return resolved


def get_track_path(track_id: str) -> Path:
    return _lookup(_TRACKS, track_id, "track")


def get_tyre_lateral_path(dataset_id: str) -> Path:
    return _lookup(_TYRE_LATERAL, dataset_id, "tyre lateral")


def get_tyre_longitudinal_path(dataset_id: str) -> Path:
    return _lookup(_TYRE_LONGITUDINAL, dataset_id, "tyre longitudinal")


def list_track_ids() -> list[str]:
    return sorted(_TRACKS.keys())


def list_tyre_lateral_ids() -> list[str]:
    return sorted(_TYRE_LATERAL.keys())


def list_tyre_longitudinal_ids() -> list[str]:
    return sorted(_TYRE_LONGITUDINAL.keys())
```

- [ ] **Step 5: Run the tests to confirm they pass**

Run: `uv run pytest tests/test_security_dataset_registry.py -v`

Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/app/security/__init__.py src/app/security/dataset_registry.py tests/test_security_dataset_registry.py
git commit -m "feat(security): add dataset registry allowlist"
```

---

## Task 2: Harden `paths.resolve_repo_path`

**Files:**
- Modify: `src/app/paths.py:85-103`
- Test: `tests/test_security_paths.py` (new)

The current implementation accepts absolute paths verbatim. We change it to a private helper used only for *trusted, hard-coded* relative paths from `config.json`, and we explicitly reject absolute paths, drive letters, and `..` segments. `resolve_track_path` is removed in a later task once all call sites stop using it.

- [ ] **Step 1: Write failing tests**

Write `tests/test_security_paths.py`:

```python
import pytest

from app.paths import resolve_repo_path


def test_resolve_repo_path_accepts_known_relative_path():
    p = resolve_repo_path("datasets/tracks/FSUK.txt")
    assert p.exists()


def test_resolve_repo_path_rejects_absolute_path():
    for hostile in ["/etc/passwd", "C:\\Windows\\System32", "/tmp/x"]:
        with pytest.raises(ValueError):
            resolve_repo_path(hostile)


def test_resolve_repo_path_rejects_parent_traversal():
    for hostile in ["../etc/passwd", "datasets/../../etc/passwd", "..\\windows"]:
        with pytest.raises(ValueError):
            resolve_repo_path(hostile)


def test_resolve_repo_path_rejects_empty():
    with pytest.raises(ValueError):
        resolve_repo_path("")
```

- [ ] **Step 2: Run the tests to confirm they fail**

Run: `uv run pytest tests/test_security_paths.py -v`

Expected: FAIL — `resolve_repo_path` currently returns the absolute path unchanged.

- [ ] **Step 3: Tighten `resolve_repo_path`**

In `src/app/paths.py`, replace lines 85-93 with:

```python
def resolve_repo_path(relative_path: str | Path) -> Path:
    if not relative_path:
        raise ValueError("relative_path must be non-empty")
    rel = Path(relative_path)
    if rel.is_absolute() or rel.drive:
        raise ValueError(f"Absolute paths are not permitted: {relative_path!r}")
    parts = rel.parts
    if ".." in parts or any(p.startswith("..") for p in parts):
        raise ValueError(f"Parent-directory traversal is not permitted: {relative_path!r}")
    return _first_existing(
        distribution_root() / rel,
        bundle_root() / rel,
        source_root() / rel,
    )
```

Also remove the existing `resolve_track_path` function (lines 96-103). Its callers are updated in Task 3 and Task 4.

- [ ] **Step 4: Run the tests to confirm they pass**

Run: `uv run pytest tests/test_security_paths.py -v`

Expected: PASS.

- [ ] **Step 5: Run the full test suite to surface regressions**

Run: `uv run pytest tests/ -v`

Expected: Existing tests that call `resolve_track_path` or that send absolute paths will FAIL. That is expected — they are fixed in Tasks 3-5. Note which tests fail so you can verify they pass after those tasks.

- [ ] **Step 6: Commit**

```bash
git add src/app/paths.py tests/test_security_paths.py
git commit -m "fix(security): reject absolute paths and traversal in resolve_repo_path"
```

---

## Task 3: Lock down tyre-verify endpoint to dataset IDs

**Files:**
- Modify: `src/app/schemas.py:18-23`
- Modify: `src/app/services/tyre_service.py:199-209`
- Modify: `src/app/static/app.js` (tyre verify fetch payload — grep for `lat_path` to find call site)
- Test: `tests/test_security_smoke.py` will exercise this in Task 10

- [ ] **Step 1: Replace the `TyreVerifyRequest` schema**

In `src/app/schemas.py`, replace lines 18-23 with:

```python
class TyreVerifyRequest(BaseModel):
    lat_dataset: str = Field(min_length=1, max_length=64)
    long_dataset: str = Field(min_length=1, max_length=64)
    model_variant: str = Field(default="tyre_peak_load_clamp", max_length=64)
    rmse_threshold_pct: float = Field(default=12.0, ge=0.0, le=100.0)
    base_mu: float = Field(default=1.0, ge=0.0, le=5.0)
```

- [ ] **Step 2: Update the service to resolve IDs via the registry**

In `src/app/services/tyre_service.py`, change the imports near the top of the file to add:

```python
from app.security.dataset_registry import get_tyre_lateral_path, get_tyre_longitudinal_path
```

Replace `run_tyre_verify`'s signature and the path-resolution block (lines 199-209). The new signature:

```python
def run_tyre_verify(
    lat_dataset: str,
    long_dataset: str,
    model_variant: str = "tyre_peak_load_clamp",
    rmse_threshold_pct: float = 12.0,
    base_mu: float = 1.0,
) -> dict:
    from vehicle.Tyres.baseTyre import LookupTableTyreModel

    try:
        full_lat  = str(get_tyre_lateral_path(lat_dataset))
        full_long = str(get_tyre_longitudinal_path(long_dataset))
    except ValueError as exc:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail=str(exc))
```

(Keep the rest of the function body — `LookupTableTyreModel.from_config(...)` and below — unchanged.)

- [ ] **Step 3: Update the FastAPI route in `web.py`**

In `src/app/web.py`, replace the `tyre_verify_endpoint` body (lines 53-61) with:

```python
    @app.post("/api/tyre/verify")
    def tyre_verify_endpoint(req: TyreVerifyRequest) -> dict:
        return run_tyre_verify(
            lat_dataset=req.lat_dataset,
            long_dataset=req.long_dataset,
            model_variant=req.model_variant,
            rmse_threshold_pct=req.rmse_threshold_pct,
            base_mu=req.base_mu,
        )
```

- [ ] **Step 4: Update the frontend**

In `src/app/static/app.js`, grep for `lat_path` and `long_path`. Replace each occurrence in the tyre-verify request body with `lat_dataset` and `long_dataset` respectively, and replace the value (which is a full path today) with the registered short ID (`"round_8_12psi"` for lateral, `"round_6_12psi"` for longitudinal). If the UI exposes a dropdown for dataset selection, source its options from a new endpoint added in Task 7. For this task, hardcode the default IDs.

- [ ] **Step 5: Run existing tyre tests**

Run: `uv run pytest tests/test_tyre_force_contracts.py tests/test_tyre_peak_load_clamp_contracts.py tests/test_tyre_validity_domain_contracts.py -v`

Expected: PASS (these don't go through the API). If any of them call `run_tyre_verify` directly with `lat_path`/`long_path`, update the call to use the new parameter names and dataset IDs.

- [ ] **Step 6: Commit**

```bash
git add src/app/schemas.py src/app/services/tyre_service.py src/app/web.py src/app/static/app.js
git commit -m "fix(security): tyre-verify endpoint accepts dataset IDs only"
```

---

## Task 4: Build the typed `ConfigOverrides` model and config builder

**Files:**
- Create: `src/app/security/config_overrides.py`
- Test: `tests/test_security_config_overrides.py`

This is the core architectural change. Instead of letting clients send an arbitrary `config: dict[str, Any]` (which today flows into `create_vehicle(cfg)` and opens whatever files the dict's keys reference), we accept a small, typed override payload and reconstruct the simulator config server-side.

- [ ] **Step 1: Write failing tests**

Write `tests/test_security_config_overrides.py`:

```python
import pytest

from app.security.config_overrides import ConfigOverrides, build_config


def _base_config():
    return {
        "powertrain": {"powertrain": "datasets/vehicle/PU_data/Honda_CBR_600RR_RPM_vs_Peak_Power.csv", "type": "lookup"},
        "track": {"file_path": "datasets/tracks/FSUK.txt"},
        "tyre_model": {
            "file_path_longit": "datasets/vehicle/tyre_data/round_6_12_psi_longit_load_tyredata_parsed.csv",
            "file_path_lateral": "datasets/vehicle/tyre_data/round_8_12_psi_lateral_load_tyredata_parsed.csv",
            "type": "lookup",
        },
        "vehicle_parameters": "parameters.json",
        "debug_mode": False,
        "full_telemetry_mode": True,
        "solver": {"use_rollover_speed_cap": True, "max_brake_decel_g": 2.0},
        "ambient_conditions": {"air_density": 1.225},
    }


def test_build_config_with_no_overrides_returns_resolved_base():
    cfg = build_config(_base_config(), ConfigOverrides())
    assert cfg["track"]["file_path"].endswith("FSUK.txt")
    assert cfg["debug_mode"] is False


def test_build_config_with_track_id_swaps_track_file():
    cfg = build_config(_base_config(), ConfigOverrides(track_id="SkidpadF26"))
    assert cfg["track"]["file_path"].endswith("SkidpadF26.txt")


def test_build_config_with_unknown_track_id_raises():
    with pytest.raises(ValueError):
        build_config(_base_config(), ConfigOverrides(track_id="not_a_real_track"))


def test_build_config_always_forces_debug_mode_off():
    base = _base_config()
    base["debug_mode"] = True
    cfg = build_config(base, ConfigOverrides())
    assert cfg["debug_mode"] is False


def test_build_config_accepts_ambient_air_density_override():
    cfg = build_config(_base_config(), ConfigOverrides(air_density=1.0))
    assert cfg["ambient_conditions"]["air_density"] == 1.0


def test_build_config_air_density_rejects_out_of_range():
    with pytest.raises(ValueError):
        ConfigOverrides(air_density=-1.0)
    with pytest.raises(ValueError):
        ConfigOverrides(air_density=999.0)


def test_build_config_accepts_max_brake_decel_override():
    cfg = build_config(_base_config(), ConfigOverrides(max_brake_decel_g=1.5))
    assert cfg["solver"]["max_brake_decel_g"] == 1.5


def test_build_config_max_brake_decel_rejects_out_of_range():
    with pytest.raises(ValueError):
        ConfigOverrides(max_brake_decel_g=-0.1)
    with pytest.raises(ValueError):
        ConfigOverrides(max_brake_decel_g=10.0)


def test_build_config_does_not_mutate_base():
    base = _base_config()
    base_copy = dict(base)
    build_config(base, ConfigOverrides(track_id="SkidpadF26"))
    assert base == base_copy
```

- [ ] **Step 2: Run the tests to confirm they fail**

Run: `uv run pytest tests/test_security_config_overrides.py -v`

Expected: ImportError for `app.security.config_overrides`.

- [ ] **Step 3: Implement the overrides module**

Write `src/app/security/config_overrides.py`:

```python
"""Server-side reconstruction of the simulator config from a typed override payload.

The simulator's full config dict references multiple dataset files (powertrain CSV,
tyre data, track file). We do not let clients touch those paths — we accept only a
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

    # Always force debug_mode off — it triggers plt.show() etc. on a headless server.
    cfg["debug_mode"] = False

    if overrides.track_id is not None:
        track_path = get_track_path(overrides.track_id)
    else:
        # Resolve the base config's relative track path through the registry only if
        # it matches a registered ID. Otherwise fall back to the file the base config
        # already points at (loaded from the trusted server-side config.json).
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
```

- [ ] **Step 4: Run the tests to confirm they pass**

Run: `uv run pytest tests/test_security_config_overrides.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/app/security/config_overrides.py tests/test_security_config_overrides.py
git commit -m "feat(security): add typed ConfigOverrides and server-side config builder"
```

---

## Task 5: Vehicle parameter allowlist

**Files:**
- Create: `src/app/security/vehicle_params.py`
- Test: `tests/test_security_vehicle_params.py`

The sweep and lift-coast services call `setattr(vehicle.params, key, value)` after only a `hasattr` check. That accepts dunder names, private attributes, and any future internal field. We replace it with an explicit allowlist of physically meaningful parameters.

- [ ] **Step 1: Write failing tests**

Write `tests/test_security_vehicle_params.py`:

```python
import pytest

from app.security.vehicle_params import canonical_or_reject, is_overridable, list_overridable_params


def test_known_param_passes():
    assert canonical_or_reject("mass") == "mass"


def test_alias_is_canonicalised():
    assert canonical_or_reject("aero_cp") == "aero_centre_of_pressure"


def test_unknown_param_rejected():
    with pytest.raises(ValueError):
        canonical_or_reject("__class__")
    with pytest.raises(ValueError):
        canonical_or_reject("not_a_real_param")


def test_dunder_attempts_rejected():
    for hostile in ["__init__", "__class__", "_private", "params.__dict__"]:
        with pytest.raises(ValueError):
            canonical_or_reject(hostile)


def test_is_overridable_matches_canonical_or_reject():
    assert is_overridable("mass")
    assert not is_overridable("__class__")


def test_list_overridable_includes_expected_subset():
    names = list_overridable_params()
    for required in ["mass", "wheelbase", "aero_centre_of_pressure", "transmission_efficiency", "final_drive_ratio", "wheel_radius"]:
        assert required in names
```

- [ ] **Step 2: Run the tests to confirm they fail**

Run: `uv run pytest tests/test_security_vehicle_params.py -v`

Expected: ImportError for `app.security.vehicle_params`.

- [ ] **Step 3: Implement the allowlist**

Write `src/app/security/vehicle_params.py`:

```python
"""Explicit allowlist of vehicle parameters that may be overridden via the API.
Replaces the prior `hasattr` check, which accepted dunder names and any private
attribute that happened to exist on `vehicle.params`."""
from __future__ import annotations

_ALIASES: dict[str, str] = {
    "aero_cp": "aero_centre_of_pressure",
}

_OVERRIDABLE: frozenset[str] = frozenset({
    "mass",
    "wheelbase",
    "cog_longitudinal_pos",
    "cog_height",
    "track_width",
    "wheel_radius",
    "final_drive_ratio",
    "transmission_efficiency",
    "aero_centre_of_pressure",
    "drag_coefficient",
    "lift_coefficient",
    "frontal_area",
    "rolling_resistance_coefficient",
})


def canonical_or_reject(name: str) -> str:
    """Return the canonical attribute name for `name`, or raise ValueError if
    `name` is not in the allowlist. Resolves aliases like `aero_cp`."""
    if not isinstance(name, str) or not name:
        raise ValueError("parameter name must be a non-empty string")
    canonical = _ALIASES.get(name, name)
    if canonical not in _OVERRIDABLE:
        raise ValueError(f"Parameter {name!r} is not overridable")
    return canonical


def is_overridable(name: str) -> bool:
    try:
        canonical_or_reject(name)
        return True
    except ValueError:
        return False


def list_overridable_params() -> list[str]:
    return sorted(_OVERRIDABLE)
```

Note: if any name in `_OVERRIDABLE` does not actually exist on `vehicle.params`, you will find out in Task 6 when the sweep tests run. Verify by opening `src/vehicle/vehicle.py` and checking the params dataclass. Remove any name that does not exist; the allowlist must be a subset of real attributes.

- [ ] **Step 4: Run the tests to confirm they pass**

Run: `uv run pytest tests/test_security_vehicle_params.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/app/security/vehicle_params.py tests/test_security_vehicle_params.py
git commit -m "feat(security): add vehicle-parameter override allowlist"
```

---

## Task 6: Apply config-overrides and param allowlist to lap and sweep services

**Files:**
- Modify: `src/app/schemas.py:6-8, 26-32`
- Modify: `src/app/services/lap_service.py:29-43`
- Modify: `src/app/services/sweep_service.py:75-128`
- Modify: `src/app/static/app.js` (lap and sweep call sites)

This task replaces the `config: dict[str, Any]` field on `LapRunRequest` and `SweepRequest` with the typed `ConfigOverrides` model from Task 4, and routes both services through `build_config`. It also routes sweep's `param` through `canonical_or_reject`.

- [ ] **Step 1: Update `LapRunRequest` and `SweepRequest` schemas**

In `src/app/schemas.py`, at the top of the file add:

```python
from app.security.config_overrides import ConfigOverrides
```

Replace `LapRunRequest` (lines 6-8) with:

```python
class LapRunRequest(BaseModel):
    parameters: dict[str, float | int | bool] | None = Field(default=None)
    overrides: ConfigOverrides = Field(default_factory=ConfigOverrides)
```

Replace `SweepRequest` (lines 26-32) with:

```python
class SweepRequest(BaseModel):
    param: str = Field(min_length=1, max_length=64)
    values: str = Field(min_length=1, max_length=512)
    steps: int = Field(default=5, ge=2, le=50)
    parameters: dict[str, float | int | bool] | None = Field(default=None)
    overrides: ConfigOverrides = Field(default_factory=ConfigOverrides)
```

Note `parameters` is now typed as `dict[str, float | int | bool]` — Pydantic will reject string-valued or nested entries at the boundary.

- [ ] **Step 2: Update `lap_service.run_lap`**

In `src/app/services/lap_service.py`, replace the function signature and body up to the existing `create_vehicle(cfg)` line. The relevant section (lines 29-43) becomes:

```python
def run_lap(parameters: dict | None = None, overrides=None) -> dict:
    from app.security.config_overrides import ConfigOverrides, build_config
    from simulator.simulator import run_lap_time_simulation
    from track.track import load_track
    from vehicle.vehicle import create_vehicle

    overrides = overrides if overrides is not None else ConfigOverrides()
    try:
        cfg = build_config(_load_base_config(), overrides)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    if parameters is not None:
        cfg["vehicle_parameters"] = parameters
```

Delete the existing block that reads `cfg = copy.deepcopy(...)`, sets `cfg["vehicle_parameters"]`, and calls `resolve_track_path` — `build_config` already handles deep-copy and track resolution. Keep everything from `try: vehicle = create_vehicle(cfg)` onwards unchanged, but **modify the response**: remove the absolute `track_file_path` field — replace it with just the track basename to avoid leaking the server filesystem layout.

The response dict's `"track_file_path"` key (line 62 of the current file) becomes:

```python
"track_file_path": Path(cfg["track"]["file_path"]).name,
```

(Add `from pathlib import Path` near the top of the file if not present.)

- [ ] **Step 3: Update the `run_lap_endpoint` route**

In `src/app/web.py`, replace `run_lap_endpoint` (lines 49-51) with:

```python
    @app.post("/api/lap/run")
    def run_lap_endpoint(req: LapRunRequest) -> dict:
        return run_lap(parameters=req.parameters, overrides=req.overrides)
```

- [ ] **Step 4: Update `sweep_service.run_sweep`**

In `src/app/services/sweep_service.py`:

Replace the imports section at the top with:

```python
import copy
import json
from typing import Any
from pathlib import Path

from fastapi import HTTPException

from app.paths import config_path
from app.security.config_overrides import ConfigOverrides, build_config
from app.security.vehicle_params import canonical_or_reject
```

Delete the `_PARAM_ALIASES` constant (line 9) — `canonical_or_reject` handles aliases now.

Replace `run_sweep`'s signature and body up through the canonical-param resolution. Replace lines 75-118 with:

```python
def run_sweep(
    param: str,
    values: str,
    steps: int = 5,
    parameters: dict | None = None,
    overrides: ConfigOverrides | None = None,
) -> dict:
    from simulator.simulator import run_lap_time_simulation
    from track.track import load_track
    from vehicle.vehicle import create_vehicle

    overrides = overrides if overrides is not None else ConfigOverrides()
    try:
        cfg = build_config(_load_base_config(), overrides)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    if parameters is not None:
        cfg["vehicle_parameters"] = parameters

    try:
        canonical_param = canonical_or_reject(param)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    try:
        probe_vehicle = create_vehicle(cfg)
    except KeyError as e:
        raise HTTPException(status_code=422, detail=f"Missing parameter: {e}")

    current_value = getattr(probe_vehicle.params, canonical_param)
    try:
        param_values = _coerce_values(values, current_value, steps)
    except (ValueError, TypeError) as e:
        raise HTTPException(status_code=422, detail=str(e))

    track = load_track(cfg["track"]["file_path"], cfg.get("debug_mode", False))
```

Add a private `_load_base_config` helper at the top of the file (matching the lap-service pattern):

```python
def _load_base_config() -> dict:
    with open(config_path(), "r", encoding="utf-8") as f:
        return json.load(f)
```

The loop body and response below stay the same. Modify the response `"track_file_path"` key to:

```python
"track_file_path": Path(cfg["track"]["file_path"]).name,
```

- [ ] **Step 5: Update the `run_sweep_endpoint` route**

In `src/app/web.py`, replace `run_sweep_endpoint` (lines 63-72) with:

```python
    @app.post("/api/sweep/run")
    def run_sweep_endpoint(req: SweepRequest) -> dict:
        return run_sweep(
            param=req.param,
            values=req.values,
            steps=req.steps,
            parameters=req.parameters,
            overrides=req.overrides,
        )
```

- [ ] **Step 6: Update the frontend lap and sweep payloads**

In `src/app/static/app.js`, grep for `'/api/lap/run'` and `'/api/sweep/run'`. For each fetch payload:

- Replace any `config: <object>` field with `overrides: <object>` and ensure the object only contains fields from `ConfigOverrides` (`track_id`, `air_density`, `max_brake_decel_g`, `use_rollover_speed_cap`, `full_telemetry_mode`). If the UI does not currently expose any of these, send an empty object `{}` or omit the field.
- Replace any `track_file_path: <string>` field on the sweep payload with `overrides.track_id: <short id>` if the UI lets the user pick a track. Otherwise omit.

- [ ] **Step 7: Update existing API tests**

Run: `uv run pytest tests/test_api_telemetry.py tests/test_api_parameters_config.py -v`

Expected: failures where tests send the old `config` key. Update each failing test to send `overrides` instead, or to send the empty body `{}` if no overrides are needed. Re-run until green.

- [ ] **Step 8: Run the full suite**

Run: `uv run pytest tests/ -v`

Expected: all tests PASS. If `test_solver_contracts.py` or others fail because they call `run_lap` directly with positional `config=...`, update the call site to pass `overrides=ConfigOverrides(...)` instead.

- [ ] **Step 9: Commit**

```bash
git add src/app/schemas.py src/app/services/lap_service.py src/app/services/sweep_service.py src/app/web.py src/app/static/app.js tests/
git commit -m "fix(security): replace untyped config dict with ConfigOverrides; allowlist sweep params"
```

---

## Task 7: Lock down lift-coast and add bounds to all list inputs

**Files:**
- Modify: `src/app/schemas.py:11-15`
- Modify: `src/app/services/lift_coast_service.py:105-109`
- Modify: `src/app/static/app.js` (lift-coast payload)

- [ ] **Step 1: Update `LiftCoastRequest`**

In `src/app/schemas.py`, replace `LiftCoastRequest` (lines 11-15) with:

```python
class LiftCoastRequest(BaseModel):
    power_limits_kw: list[float] = Field(
        default_factory=lambda: [10.0, 20.0, 30.0, 40.0, 50.0],
        min_length=1,
        max_length=10,
    )
    energy_target_kwh: float = Field(default=0.5, gt=0.0, le=10.0)
    dt: float = Field(default=0.05, gt=0.0, le=1.0)
    parameter_overrides: dict[str, float | int | bool] = Field(
        default_factory=dict,
        max_length=20,
    )

    @field_validator("power_limits_kw")
    @classmethod
    def _bound_each_power_limit(cls, v: list[float]) -> list[float]:
        for x in v:
            if not (0.0 <= x <= 1000.0):
                raise ValueError("power_limits_kw entries must be in [0, 1000]")
        return v
```

Add `field_validator` to the pydantic imports at the top of the file:

```python
from pydantic import BaseModel, Field, field_validator
```

- [ ] **Step 2: Update `lift_coast_service.run_lift_coast` to use the param allowlist**

In `src/app/services/lift_coast_service.py`, replace the loop at lines 105-109 with:

```python
    from app.security.vehicle_params import canonical_or_reject
    for key, value in (parameter_overrides or {}).items():
        try:
            canonical = canonical_or_reject(key)
        except ValueError:
            from fastapi import HTTPException
            raise HTTPException(status_code=422, detail=f"Parameter {key!r} is not overridable")
        setattr(vehicle.params, canonical, value)
```

- [ ] **Step 3: Update the frontend lift-coast payload**

In `src/app/static/app.js`, grep for `'/api/lift-coast/run'`. Confirm the request body conforms to the new bounds (no more than 10 power limits, each within [0, 1000]). If the UI allows the user to add arbitrary power limits, add a client-side cap of 10 entries.

- [ ] **Step 4: Run lift-coast-relevant tests**

Run: `uv run pytest tests/ -v -k "lift_coast or limiting"`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/app/schemas.py src/app/services/lift_coast_service.py src/app/static/app.js
git commit -m "fix(security): bound lift-coast inputs; route param overrides through allowlist"
```

---

## Task 8: Remove info-leak endpoints and add a dataset-listing endpoint

**Files:**
- Modify: `src/app/web.py:27-35, 41-47`
- Modify: `src/app/services/lap_service.py:79-89` (metadata function)
- Modify: `src/app/static/app.js` (remove `/api/workspace` fetches; consume new `/api/datasets` if added)

- [ ] **Step 1: Delete `/api/workspace`**

In `src/app/web.py`, delete the `local_workspace_root = workspace_root()` line (line 27) and the entire `get_workspace` function (lines 33-35).

- [ ] **Step 2: Sanitize `/api/config`**

The current `/api/config` returns the full base config including filesystem paths. Replace it with a response that exposes only client-relevant fields. In `src/app/web.py`, replace `get_config_endpoint` (lines 45-47) with:

```python
    @app.get("/api/config")
    def get_config_endpoint() -> dict:
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
```

- [ ] **Step 3: Sanitize the `/api/metadata` response**

In `src/app/services/lap_service.py`, replace the `metadata` function (lines 79-89) with:

```python
from pathlib import Path  # add near top if not present


def metadata() -> dict:
    cfg = _load_base_config()
    params_json = _load_base_parameters()
    default_track = cfg.get("track", {}).get("file_path", "")

    return {
        "app_name": "LGR Sim Workbench",
        "model_scope": "Quasi-static lap-time simulator (production v1)",
        "deferred_parameters": ["suspension_stiffness", "damping_coefficient"],
        "track_default": Path(default_track).name if default_track else "",
        "parameter_file_sections": list(params_json.keys()),
    }
```

- [ ] **Step 4: Add a `/api/datasets` endpoint for the frontend**

In `src/app/web.py`, after the `health` route, add:

```python
    @app.get("/api/datasets")
    def list_datasets() -> dict:
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
```

This gives the frontend a way to populate dropdowns without hardcoding IDs.

- [ ] **Step 5: Update the frontend**

In `src/app/static/app.js`:
- Grep for `/api/workspace` and delete every fetch call and any UI that displays the workspace root.
- Grep for `_workspaceRoot` and delete the cache and any code that depends on it.
- Where the UI lists tracks or tyre datasets, fetch `/api/datasets` on init and use the returned IDs to populate the relevant `<select>` elements.

- [ ] **Step 6: Run the full suite**

Run: `uv run pytest tests/ -v`

Expected: PASS. `test_api_parameters_config.py` likely needs updating to match the new sanitised `/api/config` shape — update the assertions to check the slim shape rather than the full config.

- [ ] **Step 7: Commit**

```bash
git add src/app/web.py src/app/services/lap_service.py src/app/static/app.js tests/
git commit -m "fix(security): remove /api/workspace; sanitise /api/config and /api/metadata; add /api/datasets"
```

---

## Task 9: Force headless matplotlib backend at app boot

**Files:**
- Modify: `src/app/web.py` (top of file)

The track loader and lap-time results module call `plt.show()` when `debug_mode=True`. We already force `debug_mode` off in `build_config`, but defence-in-depth says we should also force the matplotlib backend to `Agg` at import time so any stray `plt.show()` is a no-op on a headless server.

- [ ] **Step 1: Set the matplotlib backend before the first matplotlib import**

In `src/app/web.py`, at the very top of the file (before any other imports), add:

```python
import os
os.environ.setdefault("MPLBACKEND", "Agg")
```

- [ ] **Step 2: Verify the app still starts**

Run: `uv run python -c "from app.web import create_app; create_app(); print('ok')"`

Expected: `ok`.

- [ ] **Step 3: Run the full suite**

Run: `uv run pytest tests/ -v`

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add src/app/web.py
git commit -m "fix(security): force matplotlib Agg backend at app boot"
```

---

## Task 10: Adversarial security smoke test

**Files:**
- Test: `tests/test_security_smoke.py`

A single test module that exercises every attack vector closed in this plan against the live FastAPI app. This is the regression net — if any future change re-opens one of these holes, this file will fail.

- [ ] **Step 1: Write the smoke tests**

Write `tests/test_security_smoke.py`:

```python
"""Adversarial end-to-end tests. Each test sends a payload that would have
exploited a vulnerability before Phase 1, and asserts the API rejects it."""
import pytest
from fastapi.testclient import TestClient

from app.web import create_app


@pytest.fixture(scope="module")
def client():
    return TestClient(create_app())


def test_workspace_endpoint_is_gone(client):
    res = client.get("/api/workspace")
    assert res.status_code == 404


def test_config_endpoint_does_not_leak_paths(client):
    res = client.get("/api/config")
    assert res.status_code == 200
    body = res.json()
    flat = repr(body)
    assert "datasets/" not in flat
    assert "parameters.json" not in flat
    assert "powertrain" not in body
    assert "tyre_model" not in body


def test_metadata_endpoint_does_not_leak_paths(client):
    res = client.get("/api/metadata")
    assert res.status_code == 200
    body = res.json()
    assert "datasets/" not in repr(body)


def test_tyre_verify_rejects_arbitrary_path(client):
    res = client.post("/api/tyre/verify", json={
        "lat_dataset": "../../etc/passwd",
        "long_dataset": "round_6_12psi",
    })
    assert res.status_code in (400, 422)


def test_tyre_verify_rejects_absolute_path(client):
    res = client.post("/api/tyre/verify", json={
        "lat_dataset": "/etc/passwd",
        "long_dataset": "round_6_12psi",
    })
    assert res.status_code in (400, 422)


def test_tyre_verify_accepts_registered_ids(client):
    res = client.post("/api/tyre/verify", json={
        "lat_dataset": "round_8_12psi",
        "long_dataset": "round_6_12psi",
    })
    assert res.status_code == 200


def test_sweep_rejects_param_dunder(client):
    res = client.post("/api/sweep/run", json={
        "param": "__class__",
        "values": "1,2,3",
    })
    assert res.status_code == 422


def test_sweep_rejects_unknown_param(client):
    res = client.post("/api/sweep/run", json={
        "param": "not_a_real_param",
        "values": "1,2,3",
    })
    assert res.status_code == 422


def test_sweep_rejects_unknown_track_id(client):
    res = client.post("/api/sweep/run", json={
        "param": "mass",
        "values": "200,250",
        "overrides": {"track_id": "../../etc"},
    })
    assert res.status_code == 422


def test_sweep_rejects_extra_overrides_field(client):
    res = client.post("/api/sweep/run", json={
        "param": "mass",
        "values": "200,250",
        "overrides": {"track": {"file_path": "/etc/passwd"}},
    })
    assert res.status_code == 422


def test_lap_rejects_extra_overrides_field(client):
    res = client.post("/api/lap/run", json={
        "overrides": {"track": {"file_path": "/etc/passwd"}},
    })
    assert res.status_code == 422


def test_lift_coast_rejects_oversized_power_list(client):
    res = client.post("/api/lift-coast/run", json={
        "power_limits_kw": [10.0] * 11,
    })
    assert res.status_code == 422


def test_lift_coast_rejects_out_of_range_power(client):
    res = client.post("/api/lift-coast/run", json={
        "power_limits_kw": [99999.0],
    })
    assert res.status_code == 422


def test_lift_coast_rejects_dunder_override(client):
    res = client.post("/api/lift-coast/run", json={
        "power_limits_kw": [10.0],
        "parameter_overrides": {"__class__": 1},
    })
    assert res.status_code == 422


def test_lap_response_does_not_leak_absolute_paths(client):
    res = client.post("/api/lap/run", json={})
    assert res.status_code == 200
    body = res.json()
    assert "track_file_path" in body
    track_field = body["track_file_path"]
    assert track_field, "track_file_path must be non-empty so the leak check is meaningful"
    assert "datasets/" not in track_field
    assert "/" not in track_field
    assert "\\" not in track_field


def test_datasets_endpoint_returns_registered_ids(client):
    res = client.get("/api/datasets")
    assert res.status_code == 200
    body = res.json()
    assert "FSUK" in body["tracks"]
    assert "round_8_12psi" in body["tyre_lateral"]
    assert "round_6_12psi" in body["tyre_longitudinal"]
```

- [ ] **Step 2: Run the smoke suite**

Run: `uv run pytest tests/test_security_smoke.py -v`

Expected: every test PASSES. If any test fails, the corresponding earlier task missed something — fix it in that task's file rather than weakening the test.

- [ ] **Step 3: Run the entire test suite to confirm no regressions**

Run: `uv run pytest tests/ -v`

Expected: every test PASSES.

- [ ] **Step 4: Commit**

```bash
git add tests/test_security_smoke.py
git commit -m "test(security): adversarial smoke suite for Phase 1 hardening"
```

---

## Self-review checklist

After implementation, verify each item below maps to a closed vulnerability:

- [ ] Path traversal in `tyre_service.run_tyre_verify` via `lat_path`/`long_path` → Task 3
- [ ] Path traversal in `sweep_service` via `track_file_path` → Tasks 2, 4, 6
- [ ] Path traversal via `config: dict[str, Any]` injection (`cfg["track"]["file_path"]`, `cfg["powertrain"]["powertrain"]`, `cfg["tyre_model"]["..."]`) → Task 4, applied in Task 6
- [ ] Arbitrary `setattr` on `vehicle.params` via sweep `param` → Tasks 5, 6
- [ ] Arbitrary `setattr` on `vehicle.params` via lift-coast `parameter_overrides` → Tasks 5, 7
- [ ] Unbounded `power_limits_kw` → Task 7
- [ ] `/api/workspace` leaks server filesystem root → Task 8
- [ ] `/api/config`, `/api/metadata` leak filesystem paths → Task 8
- [ ] Lap and sweep responses leak absolute `track_file_path` → Tasks 6, 8 (response field truncated to basename)
- [ ] `plt.show()` hangs/crashes on headless server → Task 9 (plus `debug_mode` forced off in Task 4)

**Out of scope for Phase 1 (covered by Phases 2 and 3):**
- Authentication / authorisation (Phase 3)
- Rate limiting and request budgeting (Phase 3)
- DeepSeek API key as plain file (Phase 2: env-var secret)
- Long-running sims blocking workers (Phase 3: background job queue)
- CORS, CSP, security headers (Phase 3)
- `/api/chat` prompt-injection hardening (Phase 3)
- Pinning dependencies (Phase 2)
- Production ASGI entry, Dockerfile, Fly.io launch (Phase 2)

Phase 1 is complete when all 10 tasks above are committed and the full pytest suite plus `tests/test_security_smoke.py` are green.
