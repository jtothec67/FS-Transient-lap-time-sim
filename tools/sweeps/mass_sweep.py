# Mass sweep generator for the LGR lap-time simulator.
# Spec: docs/superpowers/specs/2026-05-13-mass-sweep-design.md
#
# Governing call: run_lap_time_simulation via app.services.lap_service.run_lap
#
# Assumptions:
# - Config and track are taken from the default config.json.
# - All vehicle parameters are taken from parameters.json unchanged.
# - Mass is the only parameter varied between runs.
# - Output is a single JSON file written atomically after all runs complete.

import argparse
import copy
import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from app.services.lap_service import _load_base_parameters, run_lap


def build_mass_range(min_kg: float, max_kg: float, step: float) -> list[float]:
    masses = []
    current = min_kg
    while current <= max_kg + step * 1e-9:
        masses.append(round(current, 10))
        current += step
    return masses


def main() -> None:
    parser = argparse.ArgumentParser(description="Sweep vehicle mass and write lap sim results to JSON.")
    parser.add_argument("--min", type=float, default=200.0, dest="min_kg")
    parser.add_argument("--max", type=float, default=300.0, dest="max_kg")
    parser.add_argument("--step", type=float, default=5.0)
    parser.add_argument("--out", type=str, default="artifacts/mass_sweep.json")
    parser.add_argument("--baseline", type=float, default=250.0)
    args = parser.parse_args()

    out_path = Path(args.out)
    if not out_path.is_absolute():
        out_path = REPO_ROOT / out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)

    base_parameters = _load_base_parameters()
    masses = build_mass_range(args.min_kg, args.max_kg, args.step)

    points = []
    track_name = None

    for mass in masses:
        params = copy.deepcopy(base_parameters)
        params["general"]["mass"] = mass

        try:
            result = run_lap(parameters=params)
        except Exception as exc:
            print(f"Run failed at mass {mass} kg: {exc}")
            sys.exit(1)

        if track_name is None:
            track_name = result["track_file_path"]

        top_speed_kmh = max(result["telemetry"]["speeds_kmh"])

        points.append({
            "mass_kg": mass,
            "lap_time_s": result["lap_time_s"],
            "top_speed_kmh": top_speed_kmh,
            "max_abs_g_lat": result["max_abs_g_lat"],
            "max_abs_g_long": result["max_abs_g_long"],
        })

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    output = {
        "generated_at": generated_at,
        "track": track_name,
        "baseline_mass_kg": args.baseline,
        "mass_kg": {
            "min": args.min_kg,
            "max": args.max_kg,
            "step": args.step,
        },
        "points": points,
    }

    out_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(f"Wrote {len(points)} points to {out_path}")


if __name__ == "__main__":
    main()
