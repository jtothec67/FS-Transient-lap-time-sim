import copy
import json
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
from simulator.util.calcSpeedProfile import backward_pass
from simulator.util.calcSpeedProfile import forward_pass
from simulator.util.calcSpeedProfile import optimise_speed_at_points
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


def pick_worked_example_index(point_speeds, forward_speeds, backward_speeds):
    point_arr = np.asarray(point_speeds)
    fwd_arr = np.asarray(forward_speeds)
    bwd_arr = np.asarray(backward_speeds)
    final_arr = np.minimum(fwd_arr, bwd_arr)

    # Prefer a braking-limited point where Pass 3 clearly constrains speed.
    brake_mask = (bwd_arr + 1e-3 < fwd_arr) & (bwd_arr + 1e-3 < point_arr)
    brake_candidates = np.where(brake_mask)[0]
    brake_candidates = brake_candidates[brake_candidates > 5]
    if len(brake_candidates) > 0:
        best = brake_candidates[np.argmax(fwd_arr[brake_candidates] - bwd_arr[brake_candidates])]
        return int(best)

    # Otherwise use an acceleration-limited point where Pass 2 is clearly active.
    accel_mask = (fwd_arr + 1e-3 < bwd_arr) & (fwd_arr + 1e-3 < point_arr)
    accel_candidates = np.where(accel_mask)[0]
    accel_candidates = accel_candidates[accel_candidates > 5]
    if len(accel_candidates) > 0:
        best = accel_candidates[np.argmax(bwd_arr[accel_candidates] - fwd_arr[accel_candidates])]
        return int(best)

    # Last fallback is the middle of the lap.
    return int(len(final_arr) // 2)


def generate_three_pass_figure(track, point_speeds, forward_speeds, backward_speeds, output_path: str):
    distances = np.array([p.distance for p in track.points], dtype=float)
    point_arr = np.asarray(point_speeds, dtype=float)
    forward_arr = np.asarray(forward_speeds, dtype=float)
    backward_arr = np.asarray(backward_speeds, dtype=float)
    final_speeds = np.minimum(forward_arr, backward_arr)

    fig = plt.figure(figsize=(11.0, 6.2))
    ax = fig.add_subplot(111)
    ax.plot(distances, point_arr, linewidth=1.5, color="#2563eb", alpha=0.85, label="Pass 1 corner ceiling")
    ax.plot(distances, forward_arr, linewidth=1.6, color="#dc2626", alpha=0.85, label="Pass 2 forward accel limit")
    ax.plot(distances, backward_arr, linewidth=1.6, color="#0f766e", alpha=0.85, label="Pass 3 backward brake limit")
    ax.plot(distances, final_speeds, linewidth=2.2, color="#111827", label="Final profile min envelope")
    ax.set_title("Three Pass Speed Profile and Final Envelope")
    ax.set_xlabel("Distance along track (m)")
    ax.set_ylabel("Speed (m/s)")
    ax.grid(True, linestyle="--", alpha=0.35)
    ax.legend(loc="upper right", fontsize=9)

    save_plot(fig, output_path)


def main():
    cfg = load_config(os.path.join(REPO_ROOT, "config.json"))
    cfg = with_b1_variant(cfg)

    track = load_track(cfg["track"]["file_path"], debug_mode=False)
    vehicle = create_vehicle(cfg)

    point_speeds, _ = optimise_speed_at_points(track.points, vehicle, cfg)
    forward_speeds, _ = forward_pass(track, vehicle, point_speeds, cfg)
    backward_speeds, _ = backward_pass(track, vehicle, point_speeds, cfg)
    final_speeds = np.minimum(np.asarray(forward_speeds), np.asarray(backward_speeds))

    out_dir = os.path.join(REPO_ROOT, "docs", "lessons", "figures", "vehicle_modelling")
    fig_path = os.path.join(out_dir, "three_pass_speed_envelope_from_sim.png")
    generate_three_pass_figure(track, point_speeds, forward_speeds, backward_speeds, fig_path)

    worked_idx = pick_worked_example_index(point_speeds, forward_speeds, backward_speeds)
    worked_distance = float(track.points[worked_idx].distance)
    worked_curvature = float(track.points[worked_idx].curvature)
    pass1_v = float(point_speeds[worked_idx])
    pass2_v = float(forward_speeds[worked_idx])
    pass3_v = float(backward_speeds[worked_idx])
    final_v = float(final_speeds[worked_idx])

    if final_v <= pass2_v + 1e-9 and final_v <= pass3_v + 1e-9:
        if pass2_v < pass3_v:
            limiting_pass = "Pass 2"
        elif pass3_v < pass2_v:
            limiting_pass = "Pass 3"
        else:
            limiting_pass = "Pass 2 and Pass 3 tie"
    else:
        limiting_pass = "Pass 1"

    lap_result = run_lap_time_simulation(track, vehicle, cfg, display=False)

    summary = {
        "track_path": cfg["track"]["file_path"],
        "model_variant": cfg.get("ab_testing", {}).get("model_variant", "baseline"),
        "worked_index": worked_idx,
        "worked_distance_m": worked_distance,
        "worked_curvature_1pm": worked_curvature,
        "pass1_corner_speed_mps": pass1_v,
        "pass2_forward_speed_mps": pass2_v,
        "pass3_backward_speed_mps": pass3_v,
        "final_speed_mps": final_v,
        "limiting_pass": limiting_pass,
        "lap_time_s": float(lap_result.lap_time),
    }

    print(f"Saved plot: {fig_path}")
    print("Three pass worked example summary")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()