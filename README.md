
# LGR Quasi-Static Lap Time Simulator 

## Purpose of this repo
Validate design decisions, and test parameters of Leeds Gryphon Racing FS25/26 car

## Description of the simulator 

This simulator is a Quasi-static, steady-state lap time sim. Fancy words. What do they mean?
- Quasi-static: Break track into small segments, at each segment, determine what's the max speed, propagate speeds forwards, and backwards, and we get a nice speed profile!
- Steady-state: We assert all forces to be resolved at any point in time. (Especially lateral and yaw balance)

A more in-depth description of the simulator can be found on the [wiki](https://github.com/LGRSimulations/LGR_FullTrackQSLapTimeSim/wiki/Description-of-Simulator)

## Setup
This project is managed with `uv`. The easiest way to run the simulator and scripts is through `uv run python <path-to-script>` so everyone uses the same dependency environment.

Most day-to-day simulation changes should be made in `config.json` and `parameters.json`.

### Prerequisites

1. Install Python

- Use a Python version compatible with `pyproject.toml` (`requires-python`).
- You can install Python from [python.org](https://www.python.org/downloads/) or let `uv` manage Python versions.

2. Install Git

- Download from [git-scm.com](https://git-scm.com/).

3. Install uv

- Official docs: [docs.astral.sh/uv](https://docs.astral.sh/uv/)

Windows (PowerShell):
```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

macOS / Linux:
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

4. (Recommended) VS Code + Python extension

- [Visual Studio Code](https://code.visualstudio.com/)
- Python extension (`ms-python.python`)

### Clone and bootstrap

From your terminal:

```bash
git clone https://github.com/LGRSimulations/LGR_FullTrackQSLapTimeSim.git
cd LGR_FullTrackQSLapTimeSim
uv sync
```

Notes:
- `uv sync` creates/updates `.venv` and installs all dependencies.
- You can run scripts without activating the environment by using `uv run ...`.
- If you want to activate manually:
  - Windows PowerShell: `.\.venv\Scripts\Activate.ps1`
  - macOS/Linux: `source .venv/bin/activate`

### Change Documentation Standard

Major engineering updates are logged in:
- `docs/MAJOR_CHANGE_LOG.md`

Use this template for every major change:
- `docs/CHANGE_ENTRY_TEMPLATE.md`

Each entry must include:
1. Problem (high-level and low-level)
2. Diagnosis
3. Solution and implementation
4. Impact and explanation

### Repository script layout

The repository has been cleaned up so user-facing scripts live under a single `tools/` directory:

- `tools/analysis/` for analysis and validation utilities
- `tools/sweeps/` for one-off test sweeps
- `tools/tracks/` for track-generation scripts

### Root run commands

You can run these from the repository root after `uv sync`:

- Simulator: `uv run python src/main.py`
- Parameter sweep: `uv run python src/sweep.py <param> <values> [--steps N]`
- A/B diagnostics: `uv run python src/ab_testing/run_ab_suite.py [flags]`
- Tyre verification (CSV/PNG/HTML): `uv run python tools/analysis/compare_tyre_model.py`
- Tyre verification with visual windows: `uv run python tools/analysis/compare_tyre_model.py --visualise`
- Corner archetypes analysis: `uv run python tools/analysis/corner_archetypes.py`
- Lift/coast sweep: `uv run python tools/sweeps/lift_coast_test.py`
- Straight-line traction test: `uv run python tools/sweeps/straight_line_test.py`
- Skidpad track generator: `uv run python tools/tracks/skidpad_creator.py`
- Straight track generator: `uv run python tools/tracks/straight_line_creator.py`

### Local Workbench (Browser UI)

A lightweight local web app scaffold is available for zip-friendly distribution and one-click use.

Run locally from source:

```powershell
powershell -ExecutionPolicy Bypass -File tools/app/launch_sim_bt.ps1
```

macOS/Linux:

```bash
bash tools/app/launch_workbench.sh
```

Port policy:
- Allowed port range is `3000-3010`.
- If requested port is busy, launcher auto-selects the first free port in that range.
- If all ports in range are busy, launch stops with an explicit error.

What it does:
- Starts a local API backend on `127.0.0.1:8787` by default.
- Opens the browser UI automatically.
- Exposes simulator-backed services (lap run and lift/coast sweep scaffold).

Build a Windows executable folder (zip-shareable):

```powershell
powershell -ExecutionPolicy Bypass -File tools/app/build_windows_exe.ps1
```

Output:
- `dist/LGRSimWorkbench/` (share this folder or zip it)

### Quick Start Cheat Sheet

Preferred workflow: use `uv`.

Run from repository root:

```bash
uv sync

# Main simulator
uv run python src/main.py

# Parameter sweep
uv run python src/sweep.py mass 250,350 --steps 5

# A/B diagnostics
uv run python src/ab_testing/run_ab_suite.py --output-dir ab_test_outputs/full_v1

# Tyre model verification
uv run python tools/analysis/compare_tyre_model.py

# Additional tools
uv run python tools/analysis/corner_archetypes.py
uv run python tools/sweeps/lift_coast_test.py
uv run python tools/sweeps/straight_line_test.py
uv run python tools/tracks/skidpad_creator.py
uv run python tools/tracks/straight_line_creator.py
```

### Running the lap time sim

- Preferred:

```bash
uv run python src/main.py
```

- Alternative after activating `.venv`:

```bash
python src/main.py
```

This runs the simulator and generates the plots/results for the track selected in `config.json`.

#### Configure the simulator 

- Refer to `config.json`, this is where we choose the datasets we want to use for the lap time sim. 
- Refer to `parameters.json`
- Datasets are found in the `datasets` folder. Datasets include Powertrain, Tyre, FSUK track data, etc.

#### Lap time sim structure

### Running the Parameter Sweeper - `sweep.py`

Run a lap time simulation while sweeping a single vehicle parameter over values.

#### Usage

From the project root:

``` bash
uv run python src/sweep.py <param> <values> [--steps N]
```

#### Arguments

- `<param>`
  Name of the vehicle parameter to sweep.
  - You can use either the internal attribute name (for example `aero_centre_of_pressure`) or the JSON key (for example `aero_cp`).

- `<values>`  
  Format depends on parameter type:
  - Numeric scalar: `min,max` for range sweep (uses `--steps`) or explicit comma list.
    Example: `250,350`
  - String: comma-separated explicit values.
    Example: `F25_IC_Car,F26_IC_Car`
  - List (for example `gear_ratios`):
    - Single list: comma-separated items
      Example: `2.75,2.0,1.667,1.304,1.208`
    - Multiple candidate lists: separate lists with `;`, and wrap each list in `[...]`
      Example: `[2.75,2.0,1.667,1.304,1.208];[3.2,2.3,1.9,1.5,1.35]`

- `--steps N` (optional)  
  Number of points in the sweep (default: 5).


#### Examples

Sweep from 250 to 350 with default steps (5) to artifacts/sweeps/mass_sweep.csv
```bash
uv run python src/sweep.py mass 250,350 --output artifacts/sweeps/mass_sweep.csv
```

Sweep with custom steps
```bash
uv run python src/sweep.py mass 250,350 --steps 10
```

Sweep using JSON key alias
```bash
uv run python src/sweep.py aero_cp 0.8,1.2 --steps 5
```

Sweep multiple gear ratio sets
```bash
uv run python src/sweep.py gear_ratios "[2.75,2.0,1.667,1.304,1.208];[3.2,2.3,1.9,1.5,1.35]"
```

#### Output

For each parameter value:
- Loads track from config.json
- Creates vehicle from config
- Runs run_lap_time_simulation
- Prints lap time results in the format:
```
mass = 250.00, Lap Time = 72.31 s
```
- If `--output` is omitted, the CSV is written to `artifacts/sweeps/data.csv`.
#### Notes

- The parameter must exist in vehicle.params
- Track path and vehicle configuration are read from config.json

### Running A/B Diagnostics (Baseline vs B1)

Run the focused A/B diagnostic matrix to compare baseline behavior against candidate model variants (including tyre changes).

From the project root:

```bash
uv run python src/ab_testing/run_ab_suite.py --output-dir ab_test_outputs/full_v1
```

#### What it runs

- Tracks: `FSUK`, `SkidpadF26`, `StraightLineTrack`
- Variants: configurable via `--variants` (default: `baseline,b1,tyre_peak_load_clamp`)
- Parameters (focused 8):
  - `downforce_coefficient`
  - `aero_cp`
  - `cog_z`
  - `front_track_width`
  - `rear_track_width`
  - `roll_stiffness`
  - `max_roll_angle_deg`
  - `base_mu`
- Levels per parameter: `low`, `nominal`, `high` (default ±20%)

#### Outputs

- `ab_runs.csv`: run-level records (status, lap time, fallback rate, fallback gate pass/fail, limiter mode breakdown)
  - Includes explicit rollover context columns: `rollover_mode` and `use_rollover_speed_cap` (always `rollover_on` / `true`)
- `ab_sensitivity.csv`: per-track/variant sensitivity summary and stale flags
- `ab_summary.md`: human-readable diagnostic summary

#### Optional flags

```bash
uv run python src/ab_testing/run_ab_suite.py --tracks FSUK,SkidpadF26 --variants baseline,tyre_peak_load_clamp --fallback-threshold 0.15 --stale-threshold 0.05 --output-dir ab_test_outputs/custom
```

Where:

- `--tracks` selects a comma-separated subset of known tracks
- `--variants` selects one or more model variants for quick A/B comparisons
- `--fallback-threshold` sets pass/fail cutoff for `fallback_rate`
- `--stale-threshold` sets stale sensitivity cutoff in seconds
- `--output-dir` selects artifact destination

### Running Tyre Model Verification

Use this script to compare TTC tyre data against the current model and produce CSV/PNG/HTML artifacts.

Default run (recommended for CI and sharing):

```bash
uv run python tools/analysis/compare_tyre_model.py
```

Run with interactive visual windows:

```bash
uv run python tools/analysis/compare_tyre_model.py --visualise
```

Run validation gate with explicit threshold:

```bash
uv run python tools/analysis/compare_tyre_model.py --validate --rmse-threshold-pct 12

Run baseline vs tyre-clamp variant quickly with strict gates:

```bash
uv run python tools/analysis/compare_tyre_model.py --validate --model-variant baseline --rmse-threshold-pct 12 --max-high-load-growth-ratio 1.35
uv run python tools/analysis/compare_tyre_model.py --validate --model-variant tyre_peak_load_clamp --rmse-threshold-pct 12 --max-high-load-growth-ratio 1.05
```
```

Main outputs are written to:
- `artifacts/tyre_validation/tyre_model_verification.csv`
- `artifacts/tyre_validation/tyre_model_verification.html`
- `artifacts/tyre_validation/*.png`

### First-Principles Migration Plan

Use the milestone checklist for physics-first simulator hardening:

- `docs/FIRST_PRINCIPLES_MIGRATION_CHECKLIST.md`

### Milestone 1 Verification (One Command)

From the project root, run:

```bash
uv run python -m unittest tests.test_limiting_case_contracts -v
uv run python tools/analysis/m1_magic_constant_scan.py --strict
```

This validates:
- limiting-case solver behavior
- equation units contracts
- sign-convention symmetry
- residual telemetry presence/finite values for solved points
- strict undocumented-constant scan for core solver files

### Milestone 2 Verification (Tyre Validity Envelope)

From the project root, run:

```bash
uv run python -m unittest tests.test_tyre_force_contracts tests.test_tyre_peak_load_clamp_contracts tests.test_tyre_validity_domain_contracts -v
uv run python tools/analysis/compare_tyre_model.py --validate --model-variant tyre_peak_load_clamp --rmse-threshold-pct 12 --max-high-load-growth-ratio 1.05 --max-out-of-domain-count -1
uv run python src/ab_testing/run_ab_suite.py --tracks StraightLineTrack --variants baseline --output-dir ab_test_outputs/m2_domain_smoke --fallback-threshold 0.15 --stale-threshold 0.05 --max-out-of-domain-count -1
```

Hard gate baseline (measured):
- FSUK baseline max `tyre_out_of_domain_total` = `129380`
- SkidpadF26 baseline max `tyre_out_of_domain_total` = `0`
- StraightLineTrack baseline max `tyre_out_of_domain_total` = `0`
- Recommended global threshold: `130000`

Strict command (fails with non-zero exit if any run exceeds threshold):

```bash
uv run python src/ab_testing/run_ab_suite.py --tracks FSUK,SkidpadF26,StraightLineTrack --variants baseline --output-dir ab_test_outputs/m2_domain_hard_gate --fallback-threshold 0.15 --stale-threshold 0.05 --max-out-of-domain-count 130000
```

Notes:
- `--max-out-of-domain-count -1` keeps out-of-domain telemetry enabled in reporting mode.
- Non-negative thresholds enable hard-gate behavior for CI.

### Command Quick Reference

From the project root:

```bash
uv sync
uv run python src/main.py
uv run python src/sweep.py mass 250,350 --steps 5
uv run python src/ab_testing/run_ab_suite.py --output-dir ab_test_outputs/full_v1
uv run python tools/analysis/compare_tyre_model.py
```


## 📬 Questions?

Open an issue or discussion! Ping me (Branson Tay) a Teams or LinkedIn message, am happy to discuss the simulator in more detail.