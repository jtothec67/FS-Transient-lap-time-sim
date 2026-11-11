import copy
import json
import math
import os
import sys

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))
SRC_ROOT = os.path.join(REPO_ROOT, "src")
if SRC_ROOT not in sys.path:
    sys.path.insert(0, SRC_ROOT)

from simulator.simulator import run_lap_time_simulation
from track.track import load_track
from vehicle.vehicle import create_vehicle


def load_config(config_path: str):
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def with_b1_variant(config: dict) -> dict:
    cfg = copy.deepcopy(config)
    cfg.setdefault("ab_testing", {})["model_variant"] = "b1"
    cfg.setdefault("solver", {})["use_rollover_speed_cap"] = True
    return cfg


def save_plot(fig, output_path: str):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def static_load_reference_ellipse(vehicle):
    g = 9.81
    normal_load = vehicle.compute_static_normal_load()
    f_lat_peak = abs(vehicle.tyre_model.get_lateral_force(slip_angle=10.0, normal_load=normal_load)) * 4.0
    f_lon_peak = abs(vehicle.tyre_model.get_longitudinal_force(slip_ratio=12.0, normal_load=normal_load)) * 4.0
    return f_lat_peak / (vehicle.params.mass * g), f_lon_peak / (vehicle.params.mass * g)


def generate_gg_envelope_figure(result, vehicle, output_path: str):
    g_lat = np.asarray(result.g_lat_channel, dtype=float)
    g_long = np.asarray(result.g_long_channel, dtype=float)
    speed_kph = np.asarray(result.final_speeds[1:], dtype=float) * 3.6

    n = min(len(g_lat), len(g_long), len(speed_kph))
    g_lat = g_lat[:n]
    g_long = g_long[:n]
    speed_kph = speed_kph[:n]

    lat_limit, long_limit = static_load_reference_ellipse(vehicle)
    theta = np.linspace(0.0, 2.0 * math.pi, 240)
    max_abs_lat = float(np.max(np.abs(g_lat))) if n else 0.0
    max_brake = float(abs(np.min(g_long))) if n else 0.0
    max_drive = float(np.max(g_long)) if n else 0.0
    used_axis = max(1.18 * max(max_abs_lat, max_brake, max_drive), 1.5)
    reference_axis = max(1.15 * max(lat_limit, long_limit), used_axis)

    fig, axes = plt.subplots(1, 2, figsize=(12.4, 5.9), sharex=False, sharey=False)
    scatter = None

    for ax, axis_limit, title in (
        (axes[0], used_axis, "Used envelope, zoomed"),
        (axes[1], reference_axis, "Static tyre-cap context"),
    ):
        scatter = ax.scatter(g_lat, g_long, c=speed_kph, cmap="plasma", s=18, alpha=0.78, linewidths=0)
        ax.plot(
            lat_limit * np.cos(theta),
            long_limit * np.sin(theta),
            linestyle="--",
            linewidth=1.5,
            color="#dc2626",
            alpha=0.72,
            label=f"Static-load reference\n{lat_limit:.2f}g lat / {long_limit:.2f}g long",
        )
        ax.set_xlim(-axis_limit, axis_limit)
        ax.set_ylim(-axis_limit, axis_limit)
        ax.set_aspect("equal", adjustable="box")
        ax.axhline(0.0, color="#111827", linewidth=0.7, linestyle="--", alpha=0.55)
        ax.axvline(0.0, color="#111827", linewidth=0.7, linestyle="--", alpha=0.55)
        ax.set_xlabel("Lateral acceleration, $g_{lat}$")
        ax.set_title(title)
        ax.grid(True, linestyle="--", alpha=0.32)

    axes[0].set_ylabel("Longitudinal acceleration, $g_{long}$")
    axes[1].legend(loc="upper right", fontsize=8)
    cbar = fig.colorbar(scatter, ax=axes.ravel().tolist(), shrink=0.92, pad=0.025)
    cbar.set_label("Speed (kph)")

    axes[0].text(
        0.03,
        0.97,
        "\n".join(
            [
                f"Lap time: {result.lap_time:.2f} s",
                f"Max |lat|: {max_abs_lat:.2f} g",
                f"Max brake: {max_brake:.2f} g",
                f"Max drive: {max_drive:.2f} g",
            ]
        ),
        transform=axes[0].transAxes,
        fontsize=9,
        va="top",
        ha="left",
        bbox={"boxstyle": "round,pad=0.35", "facecolor": "white", "edgecolor": "#d1d5db", "alpha": 0.9},
    )

    fig.suptitle("Simulator G-G Envelope, FSUK, b1, Rollover Cap Enabled")

    save_plot(fig, output_path)

    return {
        "lap_time_s": float(result.lap_time),
        "max_abs_g_lat": max_abs_lat,
        "max_brake_g": max_brake,
        "max_drive_g": max_drive,
        "figure": output_path,
    }


def main():
    cfg = load_config(os.path.join(REPO_ROOT, "config.json"))
    cfg = with_b1_variant(cfg)

    track = load_track(cfg["track"]["file_path"], debug_mode=False)
    vehicle = create_vehicle(cfg)
    result = run_lap_time_simulation(track, vehicle, cfg, display=False)

    out_dir = os.path.join(REPO_ROOT, "docs", "lessons", "figures", "vehicle_analysis_irl_vs_simulator")
    fig_path = os.path.join(out_dir, "gg_envelope_from_sim_current.png")
    summary = {
        "track_path": cfg["track"]["file_path"],
        "model_variant": cfg.get("ab_testing", {}).get("model_variant", "baseline"),
        **generate_gg_envelope_figure(result, vehicle, fig_path),
    }

    print("Vehicle analysis figure generation complete")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
