import copy
import json
import os
import sys
from collections import Counter

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))
SRC_ROOT = os.path.join(REPO_ROOT, "src")
if SRC_ROOT not in sys.path:
    sys.path.insert(0, SRC_ROOT)

from simulator.util.calcSpeedProfile import compute_speed_profile
from track.track import load_track
from vehicle.vehicle import create_vehicle


def load_config(config_path: str):
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def with_b1_variant(config: dict) -> dict:
    cfg = copy.deepcopy(config)
    cfg.setdefault("ab_testing", {})["model_variant"] = "b1"
    return cfg


def save_plot(fig, output_path: str):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def compute_g_channels(track, final_speeds):
    distances = np.asarray([p.distance for p in track.points], dtype=float)
    g_long = []
    g_lat = []
    lap_time = 0.0

    for i in range(1, len(track.points)):
        ds = track.points[i].distance - track.points[i - 1].distance
        v_prev = float(final_speeds[i - 1])
        v_curr = float(final_speeds[i])
        v_avg = 0.5 * (v_curr + v_prev)

        if ds > 0.0:
            g_long_i = ((v_curr ** 2 - v_prev ** 2) / (2.0 * ds)) / 9.81
        else:
            g_long_i = 0.0
        g_long.append(g_long_i)

        g_lat_i = (v_curr ** 2) * float(track.points[i].curvature) / 9.81
        g_lat.append(g_lat_i)

        if v_avg > 0.0 and ds > 0.0:
            lap_time += ds / v_avg

    return distances[1:], np.asarray(g_long, dtype=float), np.asarray(g_lat, dtype=float), float(lap_time)


def generate_limiter_counts_figure(diagnostics, output_path: str):
    forward_counts = Counter(diagnostics.get("forward_limiting_mode", []))
    backward_counts = Counter(diagnostics.get("backward_limiting_mode", []))

    mode_order = [
        "power_limited",
        "traction_limited",
        "brake_limited",
        "lateral_saturated",
        "corner_capped",
        "degenerate_segment",
        "initial",
        "terminal",
    ]

    x = np.arange(len(mode_order))
    width = 0.38
    forward_vals = [forward_counts.get(m, 0) for m in mode_order]
    backward_vals = [backward_counts.get(m, 0) for m in mode_order]

    fig = plt.figure(figsize=(11.2, 5.6))
    ax = fig.add_subplot(111)
    ax.bar(x - width / 2.0, forward_vals, width=width, label="Forward pass")
    ax.bar(x + width / 2.0, backward_vals, width=width, label="Backward pass")
    ax.set_title("Limiter Mode Counts by Pass")
    ax.set_ylabel("Point count")
    ax.set_xticks(x)
    ax.set_xticklabels([m.replace("_", "\n") for m in mode_order], fontsize=9)
    ax.grid(True, axis="y", linestyle="--", alpha=0.35)
    ax.legend(loc="upper right")

    save_plot(fig, output_path)

    return {
        "forward_counts": dict(forward_counts),
        "backward_counts": dict(backward_counts),
    }


def generate_solver_health_figure(diagnostics, output_path: str):
    corner_success_count = int(sum(1 for x in diagnostics.get("corner_solver_success", []) if x))
    corner_fallback_count = int(sum(1 for x in diagnostics.get("corner_fallback_used", []) if x))
    non_physical_total = int(diagnostics.get("normal_load_non_physical_events_total", 0))
    transfer_clamped_total = int(diagnostics.get("normal_load_transfer_clamped_events_total", 0))

    labels = [
        "Corner\nsolve success",
        "Corner\nfallback",
        "Non physical\nload events",
        "Transfer\nclamped",
    ]
    values = [
        corner_success_count,
        corner_fallback_count,
        non_physical_total,
        transfer_clamped_total,
    ]

    fig = plt.figure(figsize=(9.4, 5.2))
    ax = fig.add_subplot(111)
    bars = ax.bar(labels, values)
    ax.set_title("Solver and Model Health Counters")
    ax.set_ylabel("Count")
    ax.grid(True, axis="y", linestyle="--", alpha=0.35)

    for bar, value in zip(bars, values):
        ax.text(
            bar.get_x() + bar.get_width() * 0.5,
            value + max(1, 0.02 * max(values)),
            f"{value}",
            ha="center",
            va="bottom",
            fontsize=9,
        )

    save_plot(fig, output_path)

    return {
        "corner_success_count": corner_success_count,
        "corner_fallback_count": corner_fallback_count,
        "normal_load_non_physical_events_total": non_physical_total,
        "normal_load_transfer_clamped_events_total": transfer_clamped_total,
    }


def generate_budget_scale_figure(track, diagnostics, output_path: str):
    distances = np.asarray([p.distance for p in track.points], dtype=float)
    forward_budget = np.asarray(diagnostics.get("forward_combined_budget_scale", []), dtype=float)
    backward_budget = np.asarray(diagnostics.get("backward_combined_budget_scale", []), dtype=float)

    n = min(len(distances), len(forward_budget), len(backward_budget))
    distances = distances[:n]
    forward_budget = forward_budget[:n]
    backward_budget = backward_budget[:n]

    fig = plt.figure(figsize=(11.2, 5.4))
    ax = fig.add_subplot(111)
    ax.plot(distances, forward_budget, linewidth=1.6, label="Forward pass budget scale")
    ax.plot(distances, backward_budget, linewidth=1.6, label="Backward pass budget scale")
    ax.set_title("Longitudinal Budget Scale Along Lap")
    ax.set_xlabel("Distance along track (m)")
    ax.set_ylabel("Budget scale")
    ax.set_ylim(0.0, 1.05)
    ax.grid(True, linestyle="--", alpha=0.35)
    ax.legend(loc="lower left")

    save_plot(fig, output_path)


def generate_g_channels_figure(track, final_speeds, output_path: str):
    distances, g_long, g_lat, lap_time = compute_g_channels(track, final_speeds)

    fig = plt.figure(figsize=(11.2, 6.4))
    ax = fig.add_subplot(111)
    ax.plot(distances, g_lat, linewidth=1.4, label="Lateral g")
    ax.plot(distances, g_long, linewidth=1.4, label="Longitudinal g")
    ax.set_title("g-Channels From Final Speed Profile")
    ax.set_xlabel("Distance along track (m)")
    ax.set_ylabel("g")
    ax.grid(True, linestyle="--", alpha=0.35)
    ax.legend(loc="upper right")

    save_plot(fig, output_path)

    return {
        "lap_time_s": lap_time,
        "g_long_min": float(np.min(g_long)) if len(g_long) else 0.0,
        "g_long_max": float(np.max(g_long)) if len(g_long) else 0.0,
        "g_lat_min": float(np.min(g_lat)) if len(g_lat) else 0.0,
        "g_lat_max": float(np.max(g_lat)) if len(g_lat) else 0.0,
    }


def main():
    cfg = load_config(os.path.join(REPO_ROOT, "config.json"))
    cfg = with_b1_variant(cfg)

    track = load_track(cfg["track"]["file_path"], debug_mode=False)
    vehicle = create_vehicle(cfg)
    final_speeds, _, diagnostics = compute_speed_profile(track, vehicle, cfg)

    out_dir = os.path.join(REPO_ROOT, "docs", "lessons", "figures", "vehicle_modelling_diagnostics")
    limiter_fig = os.path.join(out_dir, "limiter_mode_counts_from_sim.png")
    health_fig = os.path.join(out_dir, "solver_health_counters_from_sim.png")
    budget_fig = os.path.join(out_dir, "longitudinal_budget_scale_from_sim.png")
    g_fig = os.path.join(out_dir, "g_channels_from_sim.png")

    limiter_summary = generate_limiter_counts_figure(diagnostics, limiter_fig)
    health_summary = generate_solver_health_figure(diagnostics, health_fig)
    generate_budget_scale_figure(track, diagnostics, budget_fig)
    g_summary = generate_g_channels_figure(track, final_speeds, g_fig)

    summary = {
        "track_path": cfg["track"]["file_path"],
        "model_variant": cfg.get("ab_testing", {}).get("model_variant", "baseline"),
        "figures": {
            "limiter_mode_counts": limiter_fig,
            "solver_health_counters": health_fig,
            "longitudinal_budget_scale": budget_fig,
            "g_channels": g_fig,
        },
        **limiter_summary,
        **health_summary,
        **g_summary,
    }

    print("Vehicle modelling diagnostics figure generation complete")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
