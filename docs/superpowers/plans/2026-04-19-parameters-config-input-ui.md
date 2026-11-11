# Parameters and Config Input UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the simplified Inputs panel on the base simulator page with a full Parameters and Config editor that sends complete `parameters.json` and `config.json` objects on every run.

**Architecture:** Full object replacement — frontend pre-populates from two new GET endpoints, user edits fields, and on run the complete nested objects are POSTed to `/api/lap/run`. Backend uses them directly, bypassing disk reads. `vehicle.py` is extended to accept an inline parameters dict so no file load is needed at run time.

**Tech Stack:** Python / FastAPI / Pydantic (backend), vanilla JS + HTML + CSS (frontend), pytest (tests)

---

## File Map

| File | Change |
|---|---|
| `src/vehicle/vehicle.py` | Add `params_from_dict()`, update `create_vehicle()` to branch on dict vs path |
| `src/app/schemas.py` | Replace `LapRunRequest` fields |
| `src/app/services/lap_service.py` | Rewrite `run_lap()` signature + logic, add `get_parameters()` and `get_config()` |
| `src/app/web.py` | Add `GET /api/parameters`, `GET /api/config`, update `POST /api/lap/run` handler |
| `src/app/static/styles.css` | Add inner tab strip, section header, field hint, and error styles |
| `src/app/static/index.html` | Replace inputs panel with two-tab Parameters/Config editor |
| `src/app/static/app.js` | Add `initInnerTabs`, `loadParametersAndConfig`, `populateParameters`, `populateConfig`, `collectParameters`, `collectConfig`; rewrite `runLap` |
| `tests/test_params_from_dict.py` | New — unit tests for `params_from_dict` |
| `tests/test_api_parameters_config.py` | New — integration tests for new GET endpoints and updated POST |

---

## Task 1: `vehicle.py` — inline parameter loading

**Files:**
- Modify: `src/vehicle/vehicle.py:337-389`
- Test: `tests/test_params_from_dict.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_params_from_dict.py`:

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from vehicle.vehicle import params_from_dict


SAMPLE = {
    "general": {"name": "Test", "mass": 300.0, "base_mu": 1.4},
    "aerodynamics": {
        "frontal_area": 0.7,
        "drag_coefficient": 0.8,
        "downforce_coefficient": 0.06,
        "aero_cp": 1.1,
    },
    "geometry": {
        "wheelbase": 1.5,
        "front_track_width": 1.2,
        "rear_track_width": 1.2,
        "cog_z": 0.45,
        "cog_longitudinal_pos": 0.5,
        "max_cog_z": 0.55,
    },
    "vehicle_dynamics": {
        "roll_stiffness": 20000.0,
        "suspension_stiffness": 20000,
        "damping_coefficient": 0,
        "max_roll_angle_deg": 8,
    },
    "drivetrain": {
        "wheel_radius": 0.2,
        "final_drive_ratio": 2.5,
        "gear_ratios": [2.5, 1.8],
        "transmission_efficiency": 0.93,
    },
}


def test_params_from_dict_basic_fields():
    p = params_from_dict(SAMPLE)
    assert p.name == "Test"
    assert p.mass == 300.0
    assert p.base_mu == 1.4


def test_params_from_dict_key_rename():
    p = params_from_dict(SAMPLE)
    assert p.aero_centre_of_pressure == 1.1


def test_params_from_dict_gear_ratios():
    p = params_from_dict(SAMPLE)
    assert p.gear_ratios == [2.5, 1.8]


def test_params_from_dict_all_sections():
    p = params_from_dict(SAMPLE)
    assert p.wheelbase == 1.5
    assert p.roll_stiffness == 20000.0
    assert p.transmission_efficiency == 0.93
```

- [ ] **Step 2: Run to confirm fail**

```
cd C:\Code\LGR_FullTrackQSLapTimeSim
python -m pytest tests/test_params_from_dict.py -v
```

Expected: `ImportError: cannot import name 'params_from_dict'`

- [ ] **Step 3: Add `params_from_dict` to `vehicle.py`**

Insert this function just before `load_vehicle_parameters` at line 337 of `src/vehicle/vehicle.py`:

```python
def params_from_dict(data: dict) -> vehicle_parameters:
    return vehicle_parameters(
        name=data['general']['name'],
        mass=data['general']['mass'],
        base_mu=data['general']['base_mu'],
        frontal_area=data['aerodynamics']['frontal_area'],
        drag_coefficient=data['aerodynamics']['drag_coefficient'],
        downforce_coefficient=data['aerodynamics']['downforce_coefficient'],
        aero_centre_of_pressure=data['aerodynamics']['aero_cp'],
        wheelbase=data['geometry']['wheelbase'],
        front_track_width=data['geometry']['front_track_width'],
        rear_track_width=data['geometry']['rear_track_width'],
        cog_z=data['geometry']['cog_z'],
        cog_longitudinal_pos=data['geometry']['cog_longitudinal_pos'],
        max_cog_z=data['geometry']['max_cog_z'],
        wheel_radius=data['drivetrain']['wheel_radius'],
        final_drive_ratio=data['drivetrain']['final_drive_ratio'],
        gear_ratios=data['drivetrain']['gear_ratios'],
        transmission_efficiency=data['drivetrain']['transmission_efficiency'],
        roll_stiffness=data['vehicle_dynamics']['roll_stiffness'],
        suspension_stiffness=data['vehicle_dynamics']['suspension_stiffness'],
        damping_coefficient=data['vehicle_dynamics']['damping_coefficient'],
        max_roll_angle_deg=data['vehicle_dynamics']['max_roll_angle_deg'],
    )
```

- [ ] **Step 4: Update `create_vehicle` to branch on dict vs path**

Replace the `create_vehicle` function body (lines 376-389 of `src/vehicle/vehicle.py`) with:

```python
def create_vehicle(config) -> Vehicle:
    """Create vehicle from configuration file."""
    vp = config.get('vehicle_parameters', 'parameters.json')
    if isinstance(vp, dict):
        params = params_from_dict(vp)
    else:
        params = load_vehicle_parameters(vp)
    power_unit = create_powertrain_model(config.get('powertrain', {}))
    tyre_config = dict(config.get('tyre_model', {}))
    tyre_config.setdefault('base_mu', params.base_mu)
    model_variant = str(config.get('ab_testing', {}).get('model_variant', config.get('model_variant', 'baseline'))).strip().lower()
    tyre_config.setdefault('model_variant', model_variant)
    tyre_model = create_tyre_model(tyre_config)
    loaded_vehicle = Vehicle(params, power_unit, tyre_model, config)
    return loaded_vehicle
```

- [ ] **Step 5: Run tests to confirm pass**

```
python -m pytest tests/test_params_from_dict.py -v
```

Expected: 4 tests PASSED

- [ ] **Step 6: Commit**

```
git add src/vehicle/vehicle.py tests/test_params_from_dict.py
git commit -m "feat: add params_from_dict and inline dict support in create_vehicle"
```

---

## Task 2: `schemas.py` — update `LapRunRequest`

**Files:**
- Modify: `src/app/schemas.py`

- [ ] **Step 1: Replace `LapRunRequest`**

In `src/app/schemas.py`, replace the `LapRunRequest` class:

```python
class LapRunRequest(BaseModel):
    parameters: dict[str, Any] | None = None
    config: dict[str, Any] | None = None
```

The full file becomes:

```python
from typing import Any

from pydantic import BaseModel, Field


class LapRunRequest(BaseModel):
    parameters: dict[str, Any] | None = None
    config: dict[str, Any] | None = None


class LiftCoastRequest(BaseModel):
    power_limits_kw: list[float] = Field(default_factory=lambda: [10, 20, 30, 40, 50])
    energy_target_kwh: float = 0.5
    dt: float = 0.05
    parameter_overrides: dict[str, Any] = Field(default_factory=dict)


class ChatSource(BaseModel):
    file: str
    section: str


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    history: list[dict] = Field(default_factory=list)


class ChatResponse(BaseModel):
    answer: str
    sources: list[ChatSource]
```

- [ ] **Step 2: Commit**

```
git add src/app/schemas.py
git commit -m "feat: update LapRunRequest to accept full parameters and config objects"
```

---

## Task 3: `lap_service.py` — rewrite `run_lap`, add GET helpers

**Files:**
- Modify: `src/app/services/lap_service.py`
- Test: `tests/test_api_parameters_config.py` (partial — backend unit tests)

- [ ] **Step 1: Write failing tests for `get_parameters` and `get_config`**

Create `tests/test_api_parameters_config.py`:

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from app.services.lap_service import get_parameters, get_config


def test_get_parameters_excludes_comments():
    data = get_parameters()
    assert "_comments" not in data
    assert "general" in data
    assert "aerodynamics" in data
    assert "geometry" in data
    assert "vehicle_dynamics" in data
    assert "drivetrain" in data


def test_get_config_has_expected_keys():
    data = get_config()
    assert "track" in data
    assert "powertrain" in data
    assert "tyre_model" in data
```

- [ ] **Step 2: Run to confirm fail**

```
python -m pytest tests/test_api_parameters_config.py -v
```

Expected: `ImportError: cannot import name 'get_parameters'`

- [ ] **Step 3: Rewrite `lap_service.py`**

Replace the entire contents of `src/app/services/lap_service.py` with:

```python
import copy
import json

from app.paths import config_path, parameters_path, resolve_track_path


def _load_base_config() -> dict:
    with open(config_path(), "r", encoding="utf-8") as f:
        return json.load(f)


def _load_base_parameters() -> dict:
    with open(parameters_path(), "r", encoding="utf-8") as f:
        data = json.load(f)
    data.pop("_comments", None)
    return data


def get_parameters() -> dict:
    return _load_base_parameters()


def get_config() -> dict:
    return _load_base_config()


def run_lap(parameters: dict | None = None, config: dict | None = None) -> dict:
    from simulator.simulator import run_lap_time_simulation
    from track.track import load_track
    from vehicle.vehicle import create_vehicle

    if config is None:
        cfg = copy.deepcopy(_load_base_config())
    else:
        cfg = copy.deepcopy(config)

    if parameters is not None:
        cfg["vehicle_parameters"] = parameters

    track_file_path = cfg.get("track", {}).get("file_path", "datasets/tracks/FSUK.txt")
    cfg.setdefault("track", {})["file_path"] = resolve_track_path(track_file_path)

    vehicle = create_vehicle(cfg)
    track = load_track(cfg["track"]["file_path"], cfg.get("debug_mode", False))
    result = run_lap_time_simulation(track, vehicle, cfg, display=False)

    max_abs_g_lat = max([abs(float(g)) for g in result.g_lat_channel], default=0.0)
    max_abs_g_long = max([abs(float(g)) for g in result.g_long_channel], default=0.0)

    return {
        "lap_time_s": float(result.lap_time),
        "track_file_path": cfg["track"]["file_path"],
        "points": int(len(track.points)),
        "max_abs_g_lat": max_abs_g_lat,
        "max_abs_g_long": max_abs_g_long,
        "diagnostics": {
            "fallback_rate": float(result.diagnostics.get("fallback_rate", 0.0)),
            "corner_fallback_count": int(sum(1 for x in result.diagnostics.get("corner_fallback_used", []) if x)),
        },
    }


def metadata() -> dict:
    cfg = _load_base_config()
    params_json = _load_base_parameters()

    return {
        "app_name": "LGR Sim Workbench",
        "model_scope": "Quasi-static lap-time simulator (production v1)",
        "deferred_parameters": ["suspension_stiffness", "damping_coefficient"],
        "track_default": cfg.get("track", {}).get("file_path"),
        "parameter_file_sections": list(params_json.keys()),
    }
```

- [ ] **Step 4: Run tests to confirm pass**

```
python -m pytest tests/test_api_parameters_config.py -v
```

Expected: 2 tests PASSED

- [ ] **Step 5: Commit**

```
git add src/app/services/lap_service.py tests/test_api_parameters_config.py
git commit -m "feat: rewrite run_lap to accept full parameter objects, add get_parameters and get_config helpers"
```

---

## Task 4: `web.py` — new GET endpoints, update POST handler

**Files:**
- Modify: `src/app/web.py`
- Test: `tests/test_api_parameters_config.py` (extend)

- [ ] **Step 1: Add HTTP endpoint tests to `tests/test_api_parameters_config.py`**

Append to `tests/test_api_parameters_config.py`:

```python
from fastapi.testclient import TestClient
from app.web import create_app


def test_http_get_parameters():
    client = TestClient(create_app())
    resp = client.get("/api/parameters")
    assert resp.status_code == 200
    data = resp.json()
    assert "_comments" not in data
    assert "general" in data


def test_http_get_config():
    client = TestClient(create_app())
    resp = client.get("/api/config")
    assert resp.status_code == 200
    data = resp.json()
    assert "track" in data
    assert "powertrain" in data


def test_http_post_lap_run_null_body():
    client = TestClient(create_app())
    resp = client.post("/api/lap/run", json={})
    assert resp.status_code == 200
    data = resp.json()
    assert "lap_time_s" in data
```

- [ ] **Step 2: Run to confirm new tests fail**

```
python -m pytest tests/test_api_parameters_config.py::test_http_get_parameters tests/test_api_parameters_config.py::test_http_get_config -v
```

Expected: FAILED — `GET /api/parameters` returns 404

- [ ] **Step 3: Update `web.py`**

Replace the import line and the endpoints section. The full file becomes:

```python
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.schemas import LapRunRequest, LiftCoastRequest, ChatRequest, ChatResponse
from app.services.lap_service import get_config, get_parameters, metadata, run_lap
from app.services.lift_coast_service import run_lift_coast
from app.services.chat_service import chat


def create_app() -> FastAPI:
    app = FastAPI(title="LGR Sim Workbench", version="0.1.0")

    static_root = Path(__file__).resolve().parent / "static"
    lessons_root = Path(__file__).resolve().parents[2] / "docs" / "lessons"
    app.mount("/static", StaticFiles(directory=str(static_root)), name="static")
    app.mount("/lessons", StaticFiles(directory=str(lessons_root)), name="lessons")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(static_root / "index.html")

    workspace_root = Path(__file__).resolve().parents[2]

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.get("/api/workspace")
    def get_workspace() -> dict:
        return {"root": str(workspace_root).replace("\\", "/")}

    @app.get("/api/metadata")
    def get_metadata() -> dict:
        return metadata()

    @app.get("/api/parameters")
    def get_parameters_endpoint() -> dict:
        return get_parameters()

    @app.get("/api/config")
    def get_config_endpoint() -> dict:
        return get_config()

    @app.post("/api/lap/run")
    def run_lap_endpoint(req: LapRunRequest) -> dict:
        return run_lap(parameters=req.parameters, config=req.config)

    @app.post("/api/lift-coast/run")
    def run_lift_coast_endpoint(req: LiftCoastRequest) -> dict:
        return run_lift_coast(
            power_limits_kw=req.power_limits_kw,
            energy_target_kwh=req.energy_target_kwh,
            dt=req.dt,
            parameter_overrides=req.parameter_overrides,
        )

    @app.post("/api/chat")
    def chat_endpoint(req: ChatRequest) -> ChatResponse:
        try:
            return chat(question=req.question, history=req.history)
        except FileNotFoundError:
            raise HTTPException(status_code=503, detail="Chat is not configured.")
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=str(exc))

    return app
```

- [ ] **Step 4: Run all tests**

```
python -m pytest tests/test_api_parameters_config.py -v
```

Expected: All 5 tests PASSED

- [ ] **Step 5: Commit**

```
git add src/app/web.py tests/test_api_parameters_config.py
git commit -m "feat: add GET /api/parameters and GET /api/config endpoints"
```

---

## Task 5: `styles.css` — inner tab strip, section headers, field hints, error state

**Files:**
- Modify: `src/app/static/styles.css`

- [ ] **Step 1: Append new styles to end of `styles.css`**

Add the following to the end of `src/app/static/styles.css`:

```css
/* Inner tab strip (Parameters / Config) */
.inner-tab-bar {
  display: flex;
  margin: -12px -12px 10px -12px;
  background: #E8ECF0;
  border-bottom: 1px solid #A7AEB6;
}
.inner-tab {
  background: #E8ECF0;
  border: none;
  border-right: 1px solid #A7AEB6;
  padding: 5px 12px;
  font-family: 'Inter', sans-serif;
  font-size: 0.65rem;
  letter-spacing: 1.5px;
  text-transform: uppercase;
  color: #A7AEB6;
  cursor: pointer;
}
.inner-tab.active {
  background: #FFFFFF;
  color: #101215;
  border-top: 2px solid #C1122F;
  font-weight: bold;
}
.inner-tab:hover:not(.active) { color: #101215; }

.inner-tab-section { display: none; }
.inner-tab-section.active { display: block; }

/* Section headers within a parameter group */
.field-section-header {
  font-size: 0.65rem;
  letter-spacing: 2px;
  text-transform: uppercase;
  color: #006B5C;
  font-weight: bold;
  margin-top: 12px;
  margin-bottom: 4px;
  padding-bottom: 3px;
  border-bottom: 1px solid #E8ECF0;
}
.field-section-header:first-child { margin-top: 0; }

/* Subtext hints below inputs */
.field-hint {
  font-size: 0.65rem;
  color: #A7AEB6;
  margin-top: 2px;
  margin-bottom: 4px;
  letter-spacing: 0.3px;
}

/* Inline error highlight */
input.field-error {
  border-color: #C1122F;
  background: #FFF5F5;
}

/* Checkbox row */
.field-checkbox-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
  margin-bottom: 4px;
}
.field-checkbox-row input[type="checkbox"] {
  width: auto;
  accent-color: #006B5C;
}
.field-checkbox-row label {
  font-size: 0.7rem;
  letter-spacing: 1px;
  text-transform: uppercase;
  color: #A7AEB6;
}

/* Scrollable inputs panel */
.inputs-panel {
  overflow-y: auto;
  max-height: calc(100vh - 160px);
}
```

- [ ] **Step 2: Commit**

```
git add src/app/static/styles.css
git commit -m "feat: add inner tab strip, field section, hint, and error styles"
```

---

## Task 6: `index.html` — replace inputs panel

**Files:**
- Modify: `src/app/static/index.html`

- [ ] **Step 1: Replace the inputs panel in `index.html`**

Replace the entire `<div class="panel inputs-panel">` block (lines 32-41) with:

```html
        <div class="panel inputs-panel">

          <div class="inner-tab-bar">
            <button class="inner-tab active" data-inner-tab="params-tab">Parameters</button>
            <button class="inner-tab" data-inner-tab="config-tab">Config</button>
          </div>

          <!-- Parameters tab -->
          <div id="params-tab" class="inner-tab-section active">

            <div class="field-section-header">General</div>
            <label class="field-label">Name</label>
            <input id="p-general-name" type="text" />
            <div class="field-hint">e.g. F25_IC_Car</div>
            <label class="field-label">Mass</label>
            <input id="p-general-mass" type="text" />
            <div class="field-hint">e.g. 320.0 · kg</div>
            <label class="field-label">Base Mu</label>
            <input id="p-general-base_mu" type="text" />
            <div class="field-hint">e.g. 1.5 · dimensionless</div>

            <div class="field-section-header">Aerodynamics</div>
            <label class="field-label">Frontal Area</label>
            <input id="p-aero-frontal_area" type="text" />
            <div class="field-hint">e.g. 0.75 · m2</div>
            <label class="field-label">Drag Coefficient</label>
            <input id="p-aero-drag_coefficient" type="text" />
            <div class="field-hint">e.g. 0.85 · dimensionless</div>
            <label class="field-label">Downforce Coefficient</label>
            <input id="p-aero-downforce_coefficient" type="text" />
            <div class="field-hint">e.g. 0.07 · dimensionless</div>
            <label class="field-label">Aero Centre of Pressure</label>
            <input id="p-aero-aero_cp" type="text" />
            <div class="field-hint">e.g. 1.0 · m from front axle</div>

            <div class="field-section-header">Geometry</div>
            <label class="field-label">Wheelbase</label>
            <input id="p-geom-wheelbase" type="text" />
            <div class="field-hint">e.g. 1.6 · m</div>
            <label class="field-label">Front Track Width</label>
            <input id="p-geom-front_track_width" type="text" />
            <div class="field-hint">e.g. 1.26 · m</div>
            <label class="field-label">Rear Track Width</label>
            <input id="p-geom-rear_track_width" type="text" />
            <div class="field-hint">e.g. 1.23 · m</div>
            <label class="field-label">CoG Z</label>
            <input id="p-geom-cog_z" type="text" />
            <div class="field-hint">e.g. 0.48 · m</div>
            <label class="field-label">CoG Longitudinal Position</label>
            <input id="p-geom-cog_longitudinal_pos" type="text" />
            <div class="field-hint">e.g. 0.516 · fraction of wheelbase from front axle (0 to 1)</div>
            <label class="field-label">Max CoG Z</label>
            <input id="p-geom-max_cog_z" type="text" />
            <div class="field-hint">e.g. 0.6 · m</div>

            <div class="field-section-header">Vehicle Dynamics</div>
            <label class="field-label">Roll Stiffness</label>
            <input id="p-vd-roll_stiffness" type="text" />
            <div class="field-hint">e.g. 21439.49 · Nm/rad</div>
            <label class="field-label">Suspension Stiffness</label>
            <input id="p-vd-suspension_stiffness" type="text" />
            <div class="field-hint">e.g. 21439 · N/m</div>
            <label class="field-label">Damping Coefficient</label>
            <input id="p-vd-damping_coefficient" type="text" />
            <div class="field-hint">e.g. 0 · Ns/m</div>
            <label class="field-label">Max Roll Angle</label>
            <input id="p-vd-max_roll_angle_deg" type="text" />
            <div class="field-hint">e.g. 10 · deg</div>

            <div class="field-section-header">Drivetrain</div>
            <label class="field-label">Wheel Radius</label>
            <input id="p-dt-wheel_radius" type="text" />
            <div class="field-hint">e.g. 0.2032 · m (effective rolling radius)</div>
            <label class="field-label">Final Drive Ratio</label>
            <input id="p-dt-final_drive_ratio" type="text" />
            <div class="field-hint">e.g. 2.6 · dimensionless</div>
            <label class="field-label">Gear Ratios</label>
            <input id="p-dt-gear_ratios" type="text" />
            <div class="field-hint">comma-separated, e.g. 2.75, 2, 1.667, 1.304, 1.208</div>
            <label class="field-label">Transmission Efficiency</label>
            <input id="p-dt-transmission_efficiency" type="text" />
            <div class="field-hint">e.g. 0.95 · dimensionless (0 to 1)</div>

          </div>

          <!-- Config tab -->
          <div id="config-tab" class="inner-tab-section">

            <div class="field-section-header">Powertrain</div>
            <label class="field-label">Powertrain File</label>
            <input id="c-powertrain-path" type="text" />
            <div class="field-hint">e.g. datasets/vehicle/PU_data/Honda_CBR_600RR_RPM_vs_Peak_Power.csv</div>
            <label class="field-label">Powertrain Type</label>
            <input id="c-powertrain-type" type="text" />
            <div class="field-hint">e.g. lookup</div>

            <div class="field-section-header">Track</div>
            <label class="field-label">Track File</label>
            <input id="c-track-file_path" type="text" />
            <div class="field-hint">e.g. datasets/tracks/FSUK.txt</div>

            <div class="field-section-header">Tyre Model</div>
            <label class="field-label">Longitudinal Data File</label>
            <input id="c-tyre-file_path_longit" type="text" />
            <div class="field-hint">e.g. datasets/vehicle/tyre_data/Round_6_12_PSI_Longit_Load_TyreData_parsed.csv</div>
            <label class="field-label">Lateral Data File</label>
            <input id="c-tyre-file_path_lateral" type="text" />
            <div class="field-hint">e.g. datasets/vehicle/tyre_data/Round_8_12_PSI_Lateral_Load_TyreData_parsed.csv</div>
            <label class="field-label">Tyre Model Type</label>
            <input id="c-tyre-type" type="text" />
            <div class="field-hint">e.g. lookup</div>

            <div class="field-section-header">Simulation</div>
            <div class="field-checkbox-row">
              <input type="checkbox" id="c-sim-debug_mode" />
              <label for="c-sim-debug_mode">Debug Mode</label>
            </div>
            <div class="field-checkbox-row">
              <input type="checkbox" id="c-sim-full_telemetry_mode" />
              <label for="c-sim-full_telemetry_mode">Full Telemetry Mode</label>
            </div>

            <div class="field-section-header">Ambient</div>
            <label class="field-label">Air Density</label>
            <input id="c-ambient-air_density" type="text" />
            <div class="field-hint">e.g. 1.225 · kg/m3</div>

          </div>

          <button id="runLapBtn">Run Simulation</button>
        </div>
```

- [ ] **Step 2: Verify the HTML is valid — open the app and confirm no JS errors on load**

```
cd C:\Code\LGR_FullTrackQSLapTimeSim
python src/app/run_local_app.py
```

Open `http://localhost:8000`. Confirm the base simulator tab shows the two-tab strip with Parameters and Config tabs visible. No console errors expected.

- [ ] **Step 3: Commit**

```
git add src/app/static/index.html
git commit -m "feat: replace inputs panel with parameters and config two-tab editor"
```

---

## Task 7: `app.js` — load, populate, collect, run

**Files:**
- Modify: `src/app/static/app.js`

- [ ] **Step 1: Add `initInnerTabs` function**

Insert this function after `initTabs` (after line 12 of `app.js`):

```javascript
function initInnerTabs() {
  document.querySelectorAll('.inner-tab').forEach(tab => {
    tab.addEventListener('click', () => {
      const panel = tab.closest('.panel');
      panel.querySelectorAll('.inner-tab').forEach(t => t.classList.remove('active'));
      panel.querySelectorAll('.inner-tab-section').forEach(s => s.classList.remove('active'));
      tab.classList.add('active');
      document.getElementById(tab.dataset.innerTab).classList.add('active');
    });
  });
}
```

- [ ] **Step 2: Add `populateParameters` and `populateConfig` functions**

Insert after `initInnerTabs`:

```javascript
function populateParameters(p) {
  document.getElementById('p-general-name').value = p.general?.name ?? '';
  document.getElementById('p-general-mass').value = p.general?.mass ?? '';
  document.getElementById('p-general-base_mu').value = p.general?.base_mu ?? '';
  document.getElementById('p-aero-frontal_area').value = p.aerodynamics?.frontal_area ?? '';
  document.getElementById('p-aero-drag_coefficient').value = p.aerodynamics?.drag_coefficient ?? '';
  document.getElementById('p-aero-downforce_coefficient').value = p.aerodynamics?.downforce_coefficient ?? '';
  document.getElementById('p-aero-aero_cp').value = p.aerodynamics?.aero_cp ?? '';
  document.getElementById('p-geom-wheelbase').value = p.geometry?.wheelbase ?? '';
  document.getElementById('p-geom-front_track_width').value = p.geometry?.front_track_width ?? '';
  document.getElementById('p-geom-rear_track_width').value = p.geometry?.rear_track_width ?? '';
  document.getElementById('p-geom-cog_z').value = p.geometry?.cog_z ?? '';
  document.getElementById('p-geom-cog_longitudinal_pos').value = p.geometry?.cog_longitudinal_pos ?? '';
  document.getElementById('p-geom-max_cog_z').value = p.geometry?.max_cog_z ?? '';
  document.getElementById('p-vd-roll_stiffness').value = p.vehicle_dynamics?.roll_stiffness ?? '';
  document.getElementById('p-vd-suspension_stiffness').value = p.vehicle_dynamics?.suspension_stiffness ?? '';
  document.getElementById('p-vd-damping_coefficient').value = p.vehicle_dynamics?.damping_coefficient ?? '';
  document.getElementById('p-vd-max_roll_angle_deg').value = p.vehicle_dynamics?.max_roll_angle_deg ?? '';
  document.getElementById('p-dt-wheel_radius').value = p.drivetrain?.wheel_radius ?? '';
  document.getElementById('p-dt-final_drive_ratio').value = p.drivetrain?.final_drive_ratio ?? '';
  document.getElementById('p-dt-gear_ratios').value = (p.drivetrain?.gear_ratios ?? []).join(', ');
  document.getElementById('p-dt-transmission_efficiency').value = p.drivetrain?.transmission_efficiency ?? '';
}

function populateConfig(c) {
  document.getElementById('c-powertrain-path').value = c.powertrain?.powertrain ?? '';
  document.getElementById('c-powertrain-type').value = c.powertrain?.type ?? '';
  document.getElementById('c-track-file_path').value = c.track?.file_path ?? '';
  document.getElementById('c-tyre-file_path_longit').value = c.tyre_model?.file_path_longit ?? '';
  document.getElementById('c-tyre-file_path_lateral').value = c.tyre_model?.file_path_lateral ?? '';
  document.getElementById('c-tyre-type').value = c.tyre_model?.type ?? '';
  document.getElementById('c-sim-debug_mode').checked = c.debug_mode ?? false;
  document.getElementById('c-sim-full_telemetry_mode').checked = c.full_telemetry_mode ?? true;
  document.getElementById('c-ambient-air_density').value = c.ambient_conditions?.air_density ?? '';
}

async function loadParametersAndConfig() {
  const [pRes, cRes] = await Promise.all([
    fetch('/api/parameters'),
    fetch('/api/config'),
  ]);
  const params = await pRes.json();
  const cfg = await cRes.json();
  populateParameters(params);
  populateConfig(cfg);
}
```

- [ ] **Step 3: Add `collectParameters` and `collectConfig` functions**

Insert after `loadParametersAndConfig`:

```javascript
function collectParameters() {
  const errors = [];

  function getFloat(id, label) {
    const el = document.getElementById(id);
    const val = parseFloat(el.value);
    if (isNaN(val)) {
      el.classList.add('field-error');
      errors.push(`${label} must be a number`);
    } else {
      el.classList.remove('field-error');
    }
    return val;
  }

  function getString(id) {
    const el = document.getElementById(id);
    el.classList.remove('field-error');
    return el.value.trim();
  }

  function getArray(id, label) {
    const el = document.getElementById(id);
    const parts = el.value.split(',').map(s => parseFloat(s.trim()));
    if (parts.some(isNaN)) {
      el.classList.add('field-error');
      errors.push(`${label} must be comma-separated numbers`);
    } else {
      el.classList.remove('field-error');
    }
    return parts;
  }

  const params = {
    general: {
      name: getString('p-general-name'),
      mass: getFloat('p-general-mass', 'Mass'),
      base_mu: getFloat('p-general-base_mu', 'Base mu'),
    },
    aerodynamics: {
      frontal_area: getFloat('p-aero-frontal_area', 'Frontal area'),
      drag_coefficient: getFloat('p-aero-drag_coefficient', 'Drag coefficient'),
      downforce_coefficient: getFloat('p-aero-downforce_coefficient', 'Downforce coefficient'),
      aero_cp: getFloat('p-aero-aero_cp', 'Aero CoP'),
    },
    geometry: {
      wheelbase: getFloat('p-geom-wheelbase', 'Wheelbase'),
      front_track_width: getFloat('p-geom-front_track_width', 'Front track width'),
      rear_track_width: getFloat('p-geom-rear_track_width', 'Rear track width'),
      cog_z: getFloat('p-geom-cog_z', 'CoG Z'),
      cog_longitudinal_pos: getFloat('p-geom-cog_longitudinal_pos', 'CoG longitudinal position'),
      max_cog_z: getFloat('p-geom-max_cog_z', 'Max CoG Z'),
    },
    vehicle_dynamics: {
      roll_stiffness: getFloat('p-vd-roll_stiffness', 'Roll stiffness'),
      suspension_stiffness: getFloat('p-vd-suspension_stiffness', 'Suspension stiffness'),
      damping_coefficient: getFloat('p-vd-damping_coefficient', 'Damping coefficient'),
      max_roll_angle_deg: getFloat('p-vd-max_roll_angle_deg', 'Max roll angle'),
    },
    drivetrain: {
      wheel_radius: getFloat('p-dt-wheel_radius', 'Wheel radius'),
      final_drive_ratio: getFloat('p-dt-final_drive_ratio', 'Final drive ratio'),
      gear_ratios: getArray('p-dt-gear_ratios', 'Gear ratios'),
      transmission_efficiency: getFloat('p-dt-transmission_efficiency', 'Transmission efficiency'),
    },
  };

  return { params, errors };
}

function collectConfig() {
  const errors = [];

  function getString(id) {
    const el = document.getElementById(id);
    if (el) el.classList.remove('field-error');
    return el ? el.value.trim() : '';
  }

  function getFloat(id, label) {
    const el = document.getElementById(id);
    const val = parseFloat(el.value);
    if (isNaN(val)) {
      el.classList.add('field-error');
      errors.push(`${label} must be a number`);
    } else {
      el.classList.remove('field-error');
    }
    return val;
  }

  function getBool(id) {
    return document.getElementById(id).checked;
  }

  const cfg = {
    powertrain: {
      powertrain: getString('c-powertrain-path'),
      type: getString('c-powertrain-type'),
    },
    track: {
      file_path: getString('c-track-file_path'),
    },
    tyre_model: {
      file_path_longit: getString('c-tyre-file_path_longit'),
      file_path_lateral: getString('c-tyre-file_path_lateral'),
      type: getString('c-tyre-type'),
    },
    debug_mode: getBool('c-sim-debug_mode'),
    full_telemetry_mode: getBool('c-sim-full_telemetry_mode'),
    ambient_conditions: {
      air_density: getFloat('c-ambient-air_density', 'Air density'),
    },
  };

  return { cfg, errors };
}
```

- [ ] **Step 4: Replace `runLap` function**

Replace the existing `runLap` function (lines 26-45 of `app.js`) with:

```javascript
async function runLap() {
  const { params, errors: paramErrors } = collectParameters();
  const { cfg, errors: cfgErrors } = collectConfig();
  const allErrors = [...paramErrors, ...cfgErrors];

  const out = document.getElementById('lapOutput');

  if (allErrors.length > 0) {
    out.textContent = 'Fix input errors before running.\n\n' + allErrors.join('\n');
    return;
  }

  out.textContent = 'Running...';

  const res = await fetch('/api/lap/run', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ parameters: params, config: cfg }),
  });
  const data = await res.json();
  out.textContent = JSON.stringify(data, null, 2);
}
```

- [ ] **Step 5: Update the boot section**

In the boot section (end of `app.js`), add `initInnerTabs()` and `loadParametersAndConfig()` calls. The boot block becomes:

```javascript
document.getElementById('runLapBtn').addEventListener('click', runLap);
document.getElementById('askBtn').addEventListener('click', () => toggleChatPanel());
document.getElementById('chatSubmit').addEventListener('click', sendChatMessage);
document.getElementById('chatQuestion').addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.target.disabled) sendChatMessage();
});

initTabs();
initInnerTabs();
initLessons();
loadMetadata();
loadParametersAndConfig();
positionChatPanel();
toggleChatPanel(true);
window.addEventListener('resize', positionChatPanel);
```

- [ ] **Step 6: Manual smoke test**

```
python src/app/run_local_app.py
```

Open `http://localhost:8000`. Confirm:
- Parameters tab shows all fields pre-populated with values from `parameters.json`
- Config tab shows all fields pre-populated with values from `config.json`
- Gear ratios field shows `2.75, 2, 1.667, 1.304, 1.208`
- Switching between inner tabs works
- Clicking Run Simulation with default values returns a lap result in the output panel
- Changing mass to `abc` highlights the field in red and shows an error message instead of running

- [ ] **Step 7: Run full test suite**

```
python -m pytest tests/ -v
```

Expected: All existing tests plus new tests pass. No regressions.

- [ ] **Step 8: Commit**

```
git add src/app/static/app.js
git commit -m "feat: wire up parameters and config editor with full load, populate, collect, and run"
```
