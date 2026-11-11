import copy
import json
import os
import sys

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyArrowPatch
from matplotlib.patches import Rectangle


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))
SRC_ROOT = os.path.join(REPO_ROOT, "src")
if SRC_ROOT not in sys.path:
    sys.path.insert(0, SRC_ROOT)

from simulator.simulator import run_lap_time_simulation
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


def draw_box(ax, xy, w, h, text, fc="#f3f4f6"):
    box = Rectangle(xy, w, h, facecolor=fc, edgecolor="#111827", linewidth=1.0)
    ax.add_patch(box)
    ax.text(
        xy[0] + w * 0.5,
        xy[1] + h * 0.5,
        text,
        ha="center",
        va="center",
        fontsize=9,
        color="#111827",
    )


def draw_arrow(ax, p0, p1):
    arrow = FancyArrowPatch(
        p0,
        p1,
        arrowstyle="-|>",
        mutation_scale=12,
        linewidth=1.0,
        color="#111827",
    )
    ax.add_patch(arrow)


def generate_runtime_flow_figure(output_path: str):
    fig = plt.figure(figsize=(7.0, 10.0))
    ax = fig.add_subplot(111)
    ax.set_xlim(0.0, 1.0)
    ax.set_ylim(0.0, 1.0)
    ax.axis("off")

    w = 0.54
    h = 0.105
    x = 0.23
    labels = [
        "Config + track + vehicle",
        "Pass 1\ncorner equilibrium solver",
        "Pass 2\nforward acceleration propagation",
        "Pass 3\nbackward braking propagation",
        "Final profile\npointwise minimum combine",
        "Lap integration + diagnostics",
    ]
    y_start = 0.78
    y_step = 0.14
    boxes = [(x, y_start - i * y_step, label) for i, label in enumerate(labels)]

    for x, by, text in boxes:
        draw_box(ax, (x, by), w, h, text)

    cx = x + 0.5 * w
    for i in range(len(boxes) - 1):
        y_upper = boxes[i][1]
        y_lower = boxes[i + 1][1] + h
        draw_arrow(ax, (cx, y_upper - 0.004), (cx, y_lower + 0.004))

    ax.text(0.03, 0.965, "Simulator Core Runtime Flow", fontsize=12, color="#111827")
    ax.text(
        0.03,
        0.02,
        "Pass 1 solves yaw and lateral equilibrium at each point. Pass 2 and Pass 3 enforce reachability.",
        fontsize=8,
        color="#374151",
    )

    save_plot(fig, output_path)


def generate_corner_solver_residuals_figure(track, diagnostics, output_path: str):
    distances = np.asarray([p.distance for p in track.points], dtype=float)
    lat_rel = np.asarray(diagnostics.get("corner_solver_lat_residual_rel", []), dtype=float)
    yaw_rel = np.asarray(diagnostics.get("corner_solver_yaw_residual_rel", []), dtype=float)
    fallback_used = np.asarray(diagnostics.get("corner_fallback_used", []), dtype=bool)

    n = min(len(distances), len(lat_rel), len(yaw_rel), len(fallback_used))
    distances = distances[:n]
    lat_rel = np.clip(lat_rel[:n], 1e-12, None)
    yaw_rel = np.clip(yaw_rel[:n], 1e-12, None)
    fallback_used = fallback_used[:n]

    fig = plt.figure(figsize=(11.6, 6.8))
    ax1 = fig.add_subplot(211)
    ax2 = fig.add_subplot(212, sharex=ax1)

    ax1.semilogy(distances, lat_rel, linewidth=1.3, color="#2563eb", label="Lateral residual ratio")
    ax1.semilogy(distances, yaw_rel, linewidth=1.3, color="#dc2626", label="Yaw residual ratio")
    ax1.axhline(1e-2, color="#6b7280", linestyle="--", linewidth=1.0, label="Acceptance threshold")
    ax1.set_ylabel("Relative residual")
    ax1.set_title("Corner Solver Residual Telemetry Along Track")
    ax1.grid(True, linestyle="--", alpha=0.35)
    ax1.legend(loc="upper right", fontsize=8)

    fallback_y = np.where(fallback_used, 1.0, 0.0)
    ax2.plot(distances, fallback_y, drawstyle="steps-mid", linewidth=1.3, color="#111827")
    ax2.set_xlabel("Distance along track (m)")
    ax2.set_ylabel("Fallback used")
    ax2.set_yticks([0.0, 1.0])
    ax2.set_yticklabels(["No", "Yes"])
    ax2.grid(True, linestyle="--", alpha=0.35)

    save_plot(fig, output_path)


def main():
    cfg = load_config(os.path.join(REPO_ROOT, "config.json"))
    cfg = with_b1_variant(cfg)

    track = load_track(cfg["track"]["file_path"], debug_mode=False)
    vehicle = create_vehicle(cfg)

    final_speeds, _, diagnostics = compute_speed_profile(track, vehicle, cfg)
    lap_result = run_lap_time_simulation(track, vehicle, cfg, display=False)

    out_dir = os.path.join(REPO_ROOT, "docs", "lessons", "figures", "simulator_summary")
    flow_fig = os.path.join(out_dir, "simulator_runtime_flow.png")
    residual_fig = os.path.join(out_dir, "corner_solver_residuals_from_sim.png")

    generate_runtime_flow_figure(flow_fig)
    generate_corner_solver_residuals_figure(track, diagnostics, residual_fig)

    residual_lat_rel = np.asarray(diagnostics.get("corner_solver_lat_residual_rel", []), dtype=float)
    residual_yaw_rel = np.asarray(diagnostics.get("corner_solver_yaw_residual_rel", []), dtype=float)
    fallback_used = np.asarray(diagnostics.get("corner_fallback_used", []), dtype=bool)

    summary = {
        "track_path": cfg["track"]["file_path"],
        "model_variant": cfg.get("ab_testing", {}).get("model_variant", "baseline"),
        "lap_time_s": float(lap_result.lap_time),
        "point_count": int(len(track.points)),
        "corner_fallback_count": int(np.sum(fallback_used)) if len(fallback_used) else 0,
        "corner_lat_residual_rel_p95": float(np.nanpercentile(residual_lat_rel, 95)) if len(residual_lat_rel) else 0.0,
        "corner_yaw_residual_rel_p95": float(np.nanpercentile(residual_yaw_rel, 95)) if len(residual_yaw_rel) else 0.0,
        "figures": {
            "runtime_flow": flow_fig,
            "corner_solver_residuals": residual_fig,
        },
    }

    print("Simulator summary figure generation complete")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
