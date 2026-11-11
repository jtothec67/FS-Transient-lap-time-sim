# Parameters and Config Input UI

**Date:** 2026-04-19
**Branch:** dev/bt/web-app

## Goal

Replace the simplified "Inputs" panel on the base simulator page with a full Parameters and Config editor. Engineers can view and edit the complete contents of `parameters.json` and `config.json` from the frontend, then run the simulator using those values directly.

## Approach

Full object replacement (Approach A). The frontend sends complete `parameters` and `config` objects on every run. The backend uses them directly, bypassing disk files for that run. What the user sees in the UI is exactly what the simulator runs.

## UI Layout

The left panel on the base simulator page becomes a two-tab strip: **Parameters** and **Config**. Tab styling matches the main page tab bar. The panel label "Inputs" is removed.

The Run Simulation button sits below the tab strip and is always visible regardless of active tab.

### Parameters Tab

Fields are grouped under section headers matching the keys in `parameters.json`:

- General
- Aerodynamics
- Geometry
- Vehicle Dynamics
- Drivetrain

Each field is a text input. Below each input, a subtext line shows the example value and unit derived from the `_comments` block in `parameters.json` (e.g., `e.g. 320.0 · kg`).

The `gear_ratios` field uses a text input with subtext: `comma-separated, e.g. 2.75, 2, 1.667, 1.304, 1.208`.

The `_comments` block is not rendered as a section.

### Config Tab

Fields are grouped under section headers:

- Powertrain (`powertrain.powertrain` path, `powertrain.type`)
- Track (`track.file_path`)
- Tyre Model (`tyre_model.file_path_longit`, `tyre_model.file_path_lateral`, `tyre_model.type`)
- Simulation (`debug_mode` checkbox, `full_telemetry_mode` checkbox)
- Ambient (`ambient_conditions.air_density` number input)

The `vehicle_parameters` key is hidden from the UI. It is managed by the Parameters tab and injected by the frontend on run.

## Data Flow

### On Page Load

Two parallel GET requests fetch current file contents:

- `GET /api/parameters` — returns `parameters.json` content minus `_comments`
- `GET /api/config` — returns `config.json` content

All inputs are pre-populated from these responses.

### On Run

The frontend reads every field and reconstructs the nested `parameters` and `config` objects:

- Array fields (e.g. `gear_ratios`) are split on commas and parsed to numbers
- Boolean checkboxes map to `true` / `false`
- Numeric text inputs are parsed to floats

The frontend sets `config.vehicle_parameters` to the inline parameters dict before sending.

A single POST to `/api/lap/run` carries both objects:

```json
{
  "parameters": { ... },
  "config": { ... }
}
```

### Error Handling

If any field fails to parse (bad number, empty required field), the run is blocked. The offending field is highlighted with a brief inline error message. No silent fallbacks.

### On Response

The output panel displays the lap result as before.

## Backend Changes

### New GET Endpoints (`web.py`)

- `GET /api/parameters` — reads `parameters.json`, strips `_comments`, returns JSON
- `GET /api/config` — reads `config.json`, returns JSON

### Schema (`schemas.py`)

`LapRunRequest` is updated:

- Remove `parameter_overrides: dict`
- Remove `track_file_path: str | None`
- Add `parameters: dict | None = None`
- Add `config: dict | None = None`

### Service (`lap_service.py`)

`run_lap` accepts `parameters: dict | None` and `config: dict | None`.

When both are `None` (e.g. called from CLI or tests), the service falls back to loading `config.json` and `parameters.json` from disk as before. When both are provided, disk files are not read. Partial provision (one but not the other) is not expected and not supported.

When `config["vehicle_parameters"]` is a dict, it is passed inline to `create_vehicle`. When it is a string, the existing file-load path is used as fallback.

### Vehicle Creation (`vehicle.py`)

`create_vehicle` currently reads `cfg["vehicle_parameters"]` as a file path. A one-line branch is added: if the value is a dict, use it directly; if it is a string, load from file.

## Assumptions and Limits

- Parameters and config structures are assumed stable. If a key is added to `parameters.json` or `config.json`, the UI will not automatically reflect it until the frontend is updated.
- No save-to-disk from the UI. Edits are run-scoped only.
- No validation beyond parse errors. Out-of-range values (e.g. negative mass) are passed through to the simulator.
- `gear_ratios` is the only array field. Other array-like additions would need explicit handling.
