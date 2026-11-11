import argparse
import copy
import csv
import json
import math
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from statistics import mean

SRC_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SRC_ROOT not in sys.path:
    sys.path.insert(0, SRC_ROOT)

from track.track import Track, TrackPoint
from vehicle.vehicle import create_vehicle
from simulator.simulator import run_lap_time_simulation


def load_config(config_path):
    with open(config_path, "r") as f:
        return json.load(f)


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)


def build_constant_radius_track(radius_m, point_count=120, arc_degrees=360.0):
    """Build a synthetic closed constant-radius track."""
    if radius_m <= 0:
        raise ValueError("radius_m must be positive")
    if point_count < 4:
        raise ValueError("point_count must be at least 4")

    arc_radians = math.radians(arc_degrees)
    theta = [arc_radians * i / point_count for i in range(point_count)]
    points = []
    cumulative_distance = 0.0
    prev_x = radius_m
    prev_y = 0.0
    prev_z = 0.0

    for i, angle in enumerate(theta):
        x = radius_m * math.cos(angle)
        y = radius_m * math.sin(angle)
        z = 0.0
        if i > 0:
            cumulative_distance += math.sqrt((x - prev_x) ** 2 + (y - prev_y) ** 2 + (z - prev_z) ** 2)
        heading = angle + math.pi / 2.0
        curvature = 1.0 / radius_m
        points.append(
            TrackPoint(
                distance=cumulative_distance,
                x=x,
                y=y,
                z=z,
                curvature=curvature,
                heading=heading,
                elevation_angle=0.0,
            )
        )
        prev_x, prev_y, prev_z = x, y, z

    return Track(points, is_closed=True)


def canonical_param(param_name):
    return {
        "aero_cp": "aero_centre_of_pressure",
    }.get(param_name, param_name)


def limiter_breakdown(modes):
    if not modes:
        return {}
    counts = Counter(modes)
    total = sum(counts.values())
    if total <= 0:
        return {}
    return {k: v / total for k, v in counts.items()}


def default_radius_cases():
    return [
        {"label": "tight", "radius_m": 4.0},
        {"label": "medium", "radius_m": 7.5},
        {"label": "fast", "radius_m": 12.0},
        {"label": "very_fast", "radius_m": 20.0},
    ]


def default_parameter_cases():
    return [
        "base_mu",
        "front_track_width",
        "cog_z",
        "downforce_coefficient",
    ]


def default_rollover_mode_cases():
    return [
        {"label": "rollover_on", "use_rollover_speed_cap": True},
    ]


def level_values(nominal, pct=0.2):
    if not isinstance(nominal, (int, float)):
        raise TypeError(f"Expected numeric parameter, got {type(nominal).__name__}")
    return [
        ("low", nominal * (1.0 - pct)),
        ("nominal", nominal),
        ("high", nominal * (1.0 + pct)),
    ]


def run_suite(output_dir, radius_cases, parameter_names, stale_threshold, rollover_modes):
    config_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "config.json"))
    base_config = load_config(config_path)

    rows = []
    for mode in rollover_modes:
        for case in radius_cases:
            track = build_constant_radius_track(case["radius_m"], point_count=case.get("point_count", 120))
            for param_name in parameter_names:
                attr_name = canonical_param(param_name)
                nominal_vehicle = create_vehicle(copy.deepcopy(base_config))
                nominal_value = getattr(nominal_vehicle.params, attr_name)

                for level_name, value in level_values(nominal_value, pct=0.2):
                    config = copy.deepcopy(base_config)
                    config.setdefault("ab_testing", {})["model_variant"] = "baseline"
                    config.setdefault("solver", {})["use_rollover_speed_cap"] = bool(mode["use_rollover_speed_cap"])
                    config["track"] = {
                        "file_path": f"synthetic_constant_radius:{case['radius_m']:.3f}",
                    }
                    vehicle = create_vehicle(config)
                    setattr(vehicle.params, attr_name, value)

                    row = {
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "rollover_mode": mode["label"],
                        "use_rollover_speed_cap": bool(mode["use_rollover_speed_cap"]),
                        "track_label": case["label"],
                        "radius_m": case["radius_m"],
                        "point_count": case.get("point_count", 120),
                        "parameter": param_name,
                        "parameter_attr": attr_name,
                        "level": level_name,
                        "parameter_value": value,
                        "status": "valid",
                        "reason": "",
                        "lap_time_s": "",
                        "fallback_rate": "",
                        "corner_speed_mean": "",
                        "corner_speed_std": "",
                        "solver_success_rate": "",
                        "forward_dominant_mode": "",
                        "backward_dominant_mode": "",
                        "forward_mode_breakdown": "",
                        "backward_mode_breakdown": "",
                    }

                    try:
                        result = run_lap_time_simulation(track, vehicle, config, display=False)
                        diagnostics = getattr(result, "diagnostics", {})
                        fallback_flags = diagnostics.get("corner_fallback_used", [])
                        fallback_rate = mean([1.0 if f else 0.0 for f in fallback_flags]) if fallback_flags else 0.0
                        solver_flags = diagnostics.get("corner_solver_success", [])
                        solver_rate = mean([1.0 if f else 0.0 for f in solver_flags]) if solver_flags else 0.0
                        point_speeds = list(getattr(result, "corner_speeds", []))
                        forward_modes = diagnostics.get("forward_limiting_mode", [])
                        backward_modes = diagnostics.get("backward_limiting_mode", [])
                        forward_breakdown = limiter_breakdown(forward_modes)
                        backward_breakdown = limiter_breakdown(backward_modes)

                        row.update(
                            {
                                "lap_time_s": float(result.lap_time),
                                "fallback_rate": float(fallback_rate),
                                "corner_speed_mean": float(mean(point_speeds)) if point_speeds else "",
                                "corner_speed_std": float((sum((x - mean(point_speeds)) ** 2 for x in point_speeds) / len(point_speeds)) ** 0.5) if len(point_speeds) > 1 else 0.0,
                                "solver_success_rate": float(solver_rate),
                                "forward_mode_breakdown": json.dumps(forward_breakdown, sort_keys=True),
                                "backward_mode_breakdown": json.dumps(backward_breakdown, sort_keys=True),
                                "forward_dominant_mode": max(forward_breakdown, key=forward_breakdown.get) if forward_breakdown else "",
                                "backward_dominant_mode": max(backward_breakdown, key=backward_breakdown.get) if backward_breakdown else "",
                            }
                        )
                    except Exception as exc:
                        row["status"] = "invalid"
                        row["reason"] = f"{type(exc).__name__}: {exc}"

                    rows.append(row)

    ensure_dir(output_dir)
    runs_csv = os.path.join(output_dir, "constant_radius_runs.csv")
    with open(runs_csv, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    sensitivity_rows = []
    grouped = defaultdict(list)
    for row in rows:
        if row["status"] != "valid" or row["lap_time_s"] == "":
            continue
        grouped[(row["rollover_mode"], row["track_label"], row["parameter"])].append(float(row["lap_time_s"]))

    for (rollover_mode, track_label, parameter), lap_times in grouped.items():
        delta = max(lap_times) - min(lap_times)
        sensitivity_rows.append(
            {
                "rollover_mode": rollover_mode,
                "track_label": track_label,
                "parameter": parameter,
                "delta_lap_time_s": delta,
                "stale": delta < stale_threshold,
                "samples": len(lap_times),
            }
        )

    sensitivity_csv = os.path.join(output_dir, "constant_radius_sensitivity.csv")
    with open(sensitivity_csv, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["rollover_mode", "track_label", "parameter", "delta_lap_time_s", "stale", "samples"])
        writer.writeheader()
        writer.writerows(sensitivity_rows)

    invalid_count = sum(1 for row in rows if row["status"] == "invalid")
    md_path = os.path.join(output_dir, "constant_radius_summary.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# Constant Radius Diagnostic Summary\n\n")
        f.write(f"- Generated: {datetime.now(timezone.utc).isoformat()}\n")
        f.write(f"- Total runs: {len(rows)}\n")
        f.write(f"- Invalid runs: {invalid_count}\n")
        f.write("- Radii: " + ", ".join(f"{c['label']}={c['radius_m']}m" for c in radius_cases) + "\n")
        f.write("- Rollover modes: " + ", ".join(m["label"] for m in rollover_modes) + "\n")
        f.write("- Parameters: " + ", ".join(parameter_names) + "\n\n")
        f.write("## Notes\n\n")
        f.write("- These are synthetic closed constant-radius tracks built to isolate steady-state solver behavior.\n")
        f.write("- Runs are now always rollover-constrained to keep outputs physically realistic.\n\n")

        f.write("## Stale Parameter Count\n\n")
        stale_count = Counter((r["rollover_mode"], r["track_label"]) for r in sensitivity_rows if r["stale"])
        for mode in rollover_modes:
            f.write(f"### {mode['label']}\n\n")
            for case in radius_cases:
                f.write(f"- {case['label']}: {stale_count.get((mode['label'], case['label']), 0)} stale parameters\n")
            f.write("\n")

        f.write("## Top Sensitivity Movers\n\n")
        for row in sorted(sensitivity_rows, key=lambda r: r["delta_lap_time_s"], reverse=True)[:12]:
            f.write(
                f"- {row['rollover_mode']} / {row['track_label']} / {row['parameter']}: "
                f"delta_lap_time_s={row['delta_lap_time_s']:.6f}, stale={row['stale']}\n"
            )

    return runs_csv, sensitivity_csv, md_path


def main():
    parser = argparse.ArgumentParser(description="Run constant-radius diagnostics for the simulator.")
    parser.add_argument("--output-dir", default=os.path.join("artifacts", "diagnostics", "constant_radius_suite"), help="Directory for generated artifacts")
    parser.add_argument("--stale-threshold", type=float, default=0.05, help="Delta lap-time cutoff for stale sensitivity")
    parser.add_argument("--radii", default="", help="Optional comma-separated radii in meters")
    parser.add_argument("--parameters", default="", help="Optional comma-separated parameter names")
    args = parser.parse_args()

    if args.radii.strip():
        radius_cases = []
        for item in [v.strip() for v in args.radii.split(",") if v.strip()]:
            radius_cases.append({"label": f"r_{item.replace('.', '_')}", "radius_m": float(item)})
    else:
        radius_cases = default_radius_cases()

    if args.parameters.strip():
        parameter_names = [v.strip() for v in args.parameters.split(",") if v.strip()]
    else:
        parameter_names = default_parameter_cases()

    rollover_modes = default_rollover_mode_cases()

    runs_csv, sensitivity_csv, md_path = run_suite(
        output_dir=args.output_dir,
        radius_cases=radius_cases,
        parameter_names=parameter_names,
        stale_threshold=args.stale_threshold,
        rollover_modes=rollover_modes,
    )

    print("Constant radius diagnostic suite complete")
    print(f"Runs CSV: {runs_csv}")
    print(f"Sensitivity CSV: {sensitivity_csv}")
    print(f"Summary Markdown: {md_path}")


if __name__ == "__main__":
    main()
