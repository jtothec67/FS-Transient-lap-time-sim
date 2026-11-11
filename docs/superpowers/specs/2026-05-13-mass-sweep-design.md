# Mass Sweep Static JSON — Design

Date 2026-05-13.

## Goal
Produce a small static JSON file from the simulator that powers a single mass slider on the user's personal website. The slider reads lap time, top speed, and peak g loads as a visitor drags mass across the Formula Student range.

The slider is not built here. This spec covers only the generator script and its output contract.

## Scope
One CLI script that runs the existing lap simulator across a mass sweep and writes one JSON file. No HTTP route. No UI. No new abstractions.

Out of scope.

- Generic parameter sweep service
- Live sweep endpoint in the local app
- The website slider itself
- Multi-track sweeps

## Inputs
Defaults baked into the script.

- Mass range 200 to 300 kg
- Step 5 kg, so 21 points
- Baseline mass 250 kg (Formula Student car with driver)
- Track is whatever `config.json` already points at
- All other vehicle parameters are taken from `parameters.json` unchanged

CLI flags, all optional.

- `--min` float, default 200
- `--max` float, default 300
- `--step` float, default 5
- `--out` path, default `artifacts/mass_sweep.json`
- `--baseline` float, default 250

## Architecture
A single Python script at `tools/sweeps/mass_sweep.py`.

The script imports the existing `app.services.lap_service.run_lap` and the parameter loader. For each mass in the sweep it does the following.

1. Deep copy the base parameters loaded from `parameters.json`
2. Overwrite `vehicle.mass`
3. Call `run_lap(parameters=...)`
4. Extract `lap_time_s`, `max_abs_g_lat`, `max_abs_g_long`, and the top speed from the `telemetry.speeds_kmh` channel
5. Append a record

After the loop, write the JSON file in one go. No partial writes.

This reuses the production code path. No new wiring, no duplicated config logic.

### Why reuse `lap_service.run_lap`
`run_lap` already handles config loading, parameter substitution, vehicle creation, track loading, and the simulator call. It returns everything we need on its result dict. Calling it once per mass is the simplest correct thing.

### Top speed extraction
`run_lap` returns `telemetry.speeds_kmh` already in km/h. Top speed for the sweep record is `max(telemetry.speeds_kmh)`.

## Output JSON Schema
Single file. UTF-8. Pretty-printed with two-space indent for readability.

```json
{
  "generated_at": "2026-05-13T12:34:56Z",
  "track": "<track filename from run_lap result>",
  "baseline_mass_kg": 250,
  "mass_kg": { "min": 200, "max": 300, "step": 5 },
  "points": [
    {
      "mass_kg": 200,
      "lap_time_s": 78.42,
      "top_speed_kmh": 112.3,
      "max_abs_g_lat": 1.84,
      "max_abs_g_long": 1.51
    }
  ]
}
```

Field notes.

- `generated_at` is an ISO 8601 UTC timestamp. The website can show "snapshot from <date>" so visitors know the data is a frozen sample.
- `track` is the filename only, taken from the `track_file_path` field returned by `run_lap`.
- `baseline_mass_kg` lets the slider highlight the FS-with-driver reference point without scanning the array.
- `mass_kg` block tells the slider its range without needing to inspect every point.
- `points` is ordered ascending by mass. The slider can index into it directly.

Numeric values are written with full Python precision. The website can round at display time.

## Error Handling
If `run_lap` raises for any mass, the script prints the failing mass and exits non-zero. No partial JSON is written. A half-written sweep is worse than none for a static asset.

If `--out` points at a directory that does not exist, the script creates it before writing.

## File Header
The script begins with a short comment block per the repo's trust model.

- States the governing call (`run_lap_time_simulation` via `lap_service.run_lap`)
- Lists assumptions (default config, default track, mass is the only varied parameter, all other parameters held at `parameters.json` values)

## Testing
One pytest test at `tests/test_mass_sweep.py`.

The test invokes the script as a subprocess with `--min 250 --max 260 --step 5 --out <tmp_path>/sweep.json`, then asserts.

- Exit code is 0
- The output file exists and parses as JSON
- `points` has exactly 3 entries with `mass_kg` values 250, 255, 260
- `mass_kg` block matches the flags
- Each point has all four numeric fields and they are finite floats

The test does not assert physical values. The simulator has its own tests for that. This test only proves the pipeline produces a well-formed file.

## Definition of Done
- `tools/sweeps/mass_sweep.py` exists and runs with no arguments to produce `artifacts/mass_sweep.json`
- The output file matches the schema in this spec
- `tests/test_mass_sweep.py` passes
- A short note in the script header points to this spec file

## Trust Notes for Future Website Page
When the user wires the slider on the personal website, the page should display.

- High level. Lap time is computed by a quasi static lap simulator that finds the maximum speed at every point on the track given tyre and aero limits.
- Low level. Each mass value triggers a full lap simulation through `simulator.run_lap_time_simulation` with the standard config and track. Only mass changes between runs.
- Snapshot date from `generated_at`.

These are notes for the website work, not for this script.
