import argparse
import copy
import csv
import json
import math
import os
import sys
from datetime import datetime, timezone

import matplotlib.pyplot as plt
import numpy as np

SRC_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SRC_ROOT not in sys.path:
    sys.path.insert(0, SRC_ROOT)

from simulator.simulator import run_lap_time_simulation
from track.track import load_track
from vehicle.vehicle import create_vehicle


def load_config(config_path):
    with open(config_path, "r") as f:
        return json.load(f)


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)


def run_mode(base_config, track_path):
    config = copy.deepcopy(base_config)
    config["track"] = {"file_path": track_path}
    config.setdefault("solver", {})["use_rollover_speed_cap"] = True
    vehicle = create_vehicle(config)
    track = load_track(track_path, config.get("debug_mode", False))
    result = run_lap_time_simulation(track, vehicle, config, display=False)

    g_lat = np.asarray(result.g_lat_channel, dtype=float)
    g_long = np.asarray(result.g_long_channel, dtype=float)
    g_total = np.sqrt(g_lat**2 + g_long**2)
    speed_kph = np.asarray(result.final_speeds, dtype=float) * 3.6

    return {
        "rollover_on": True,
        "lap_time_s": float(result.lap_time),
        "g_lat": g_lat,
        "g_long": g_long,
        "g_total": g_total,
        "speed_kph": speed_kph,
        "track": track,
        "vehicle": vehicle,
        "result": result,
    }


def plot_mode(output_path, mode_label, g_lat, g_long, speed_kph, vehicle, lap_time_s):
    fig, ax = plt.subplots(figsize=(8, 8))
    scatter = ax.scatter(g_lat, g_long, c=speed_kph[1:], cmap="plasma", s=18, alpha=0.75)
    cbar = fig.colorbar(scatter, ax=ax)
    cbar.set_label("Speed (kph)")

    g = 9.81
    normal_load = vehicle.compute_static_normal_load()
    f_lat_peak = abs(vehicle.tyre_model.get_lateral_force(slip_angle=10.0, normal_load=normal_load)) * 4.0
    f_lon_peak = abs(vehicle.tyre_model.get_longitudinal_force(slip_ratio=12.0, normal_load=normal_load)) * 4.0
    a_lat_limit = f_lat_peak / (vehicle.params.mass * g)
    a_lon_limit = f_lon_peak / (vehicle.params.mass * g)

    theta = np.linspace(0.0, 2.0 * math.pi, 240)
    ax.plot(
        a_lat_limit * np.cos(theta),
        a_lon_limit * np.sin(theta),
        linestyle="--",
        linewidth=1.5,
        color="crimson",
        alpha=0.7,
        label=f"Static-load friction ellipse ({a_lat_limit:.2f}g / {a_lon_limit:.2f}g)",
    )

    ax.axhline(0.0, color="black", linewidth=0.6, linestyle="--", alpha=0.5)
    ax.axvline(0.0, color="black", linewidth=0.6, linestyle="--", alpha=0.5)
    ax.set_xlabel("Lateral Acceleration (g)")
    ax.set_ylabel("Longitudinal Acceleration (g)")
    ax.set_title(f"G-G-V: {mode_label} | lap {lap_time_s:.2f} s")
    ax.grid(True, linestyle="--", alpha=0.35)
    ax.legend(loc="best")
    fig.tight_layout()
    fig.savefig(output_path, dpi=160)
    plt.close(fig)


def write_rows_csv(path, rows):
    fieldnames = [
        "mode",
        "point_index",
        "distance_m",
        "curvature",
        "speed_mps",
        "speed_kph",
        "g_lat",
        "g_long",
        "g_total",
    ]
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description="Run rollover-constrained G-G diagnostics for the default vehicle.")
    parser.add_argument("--track", default="datasets/tracks/FSUK.txt", help="Track file path to evaluate")
    parser.add_argument("--output-dir", default=os.path.join("artifacts", "diagnostics", "gg_rollover_suite"), help="Directory for generated artifacts")
    args = parser.parse_args()

    config_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "config.json"))
    base_config = load_config(config_path)

    ensure_dir(args.output_dir)

    payload = run_mode(base_config, args.track)
    mode_label = "rollover_on"
    result = payload["result"]
    g_lat = payload["g_lat"]
    g_long = payload["g_long"]
    g_total = payload["g_total"]
    speed_kph = payload["speed_kph"]
    track = payload["track"]
    vehicle = payload["vehicle"]

    summary_rows = [
        {
            "mode": mode_label,
            "lap_time_s": payload["lap_time_s"],
            "g_lat_max_abs": float(np.max(np.abs(g_lat))) if g_lat.size else 0.0,
            "g_long_max_abs": float(np.max(np.abs(g_long))) if g_long.size else 0.0,
            "g_total_max": float(np.max(g_total)) if g_total.size else 0.0,
            "g_total_p90": float(np.percentile(g_total, 90)) if g_total.size else 0.0,
            "g_lat_p90_abs": float(np.percentile(np.abs(g_lat), 90)) if g_lat.size else 0.0,
            "g_long_p90_abs": float(np.percentile(np.abs(g_long), 90)) if g_long.size else 0.0,
            "corner_fallback_rate": float(np.mean(result.diagnostics.get("corner_fallback_used", []))) if result.diagnostics.get("corner_fallback_used") else 0.0,
            "solver_success_rate": float(np.mean(result.diagnostics.get("corner_solver_success", []))) if result.diagnostics.get("corner_solver_success") else 0.0,
        }
    ]

    channel_rows = []
    for i, point in enumerate(track.points):
        if i == 0 or i >= len(result.g_lat_channel) + 1:
            continue
        channel_rows.append(
            {
                "mode": mode_label,
                "point_index": i,
                "distance_m": float(point.distance),
                "curvature": float(point.curvature),
                "speed_mps": float(result.final_speeds[i]),
                "speed_kph": float(speed_kph[i]),
                "g_lat": float(g_lat[i - 1]),
                "g_long": float(g_long[i - 1]),
                "g_total": float(g_total[i - 1]),
            }
        )

    plot_mode(
        output_path=os.path.join(args.output_dir, "rollover_ggv.png"),
        mode_label=mode_label,
        g_lat=g_lat,
        g_long=g_long,
        speed_kph=speed_kph,
        vehicle=vehicle,
        lap_time_s=payload["lap_time_s"],
    )

    summary_csv = os.path.join(args.output_dir, "gg_rollover_summary.csv")
    with open(summary_csv, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(summary_rows[0].keys()))
        writer.writeheader()
        writer.writerows(summary_rows)

    channel_csv = os.path.join(args.output_dir, "gg_rollover_channels.csv")
    write_rows_csv(channel_csv, channel_rows)

    md_path = os.path.join(args.output_dir, "gg_rollover_summary.md")
    summary = summary_rows[0]

    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# G-G Rollover-Constrained Diagnostic Summary\n\n")
        f.write(f"- Generated: {datetime.now(timezone.utc).isoformat()}\n")
        f.write(f"- Track: {args.track}\n")
        f.write("- Vehicle: default parameters from config.json / parameters.json\n\n")
        f.write("## Summary\n\n")
        f.write(f"- mode: {summary['mode']}\n")
        f.write(f"- lap time: {summary['lap_time_s']:.3f} s\n")
        f.write(f"- max |g_lat|: {summary['g_lat_max_abs']:.3f} g\n")
        f.write(f"- max g_total: {summary['g_total_max']:.3f} g\n")
        f.write(f"- p90 |g_lat|: {summary['g_lat_p90_abs']:.3f} g\n")
        f.write(f"- p90 g_total: {summary['g_total_p90']:.3f} g\n\n")

        f.write("## Heuristic Read\n\n")
        f.write("- This diagnostic now runs only in rollover-constrained mode to stay aligned with realistic operation.\n")
        f.write("- A Formula Student car can plausibly sit around 1.5 g to 2.5 g lateral in a strong setup, but total combined g above 3 g is usually optimistic unless the model has significant aero and the solver is not overly generous.\n")
        f.write("- Inspect the G-G-V cloud against the ellipse plot and fallback diagnostics before treating lap-time changes as physical gains.\n\n")

        f.write("## Files\n\n")
        f.write(f"- Summary CSV: {summary_csv}\n")
        f.write(f"- Channel CSV: {channel_csv}\n")
        f.write(f"- Plot: {os.path.join(args.output_dir, 'rollover_ggv.png')}\n")

    print("G-G rollover diagnostic complete")
    print(f"Summary CSV: {summary_csv}")
    print(f"Channel CSV: {channel_csv}")
    print(f"Summary Markdown: {md_path}")


if __name__ == "__main__":
    main()