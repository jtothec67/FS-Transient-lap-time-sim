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
from simulator.util.calcSpeedProfile import _compute_normal_loads_for_longitudinal
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


def generate_aero_forces_vs_speed(vehicle, output_path: str):
    speeds = np.linspace(0.0, 45.0, 150)
    drag = [vehicle.compute_aero_drag(float(v)) for v in speeds]
    down = [vehicle.compute_downforce(float(v)) for v in speeds]

    fig = plt.figure(figsize=(9.0, 5.5))
    ax = fig.add_subplot(111)
    ax.plot(speeds, drag, linewidth=2.2, color="#b91c1c", label="Drag force")
    ax.plot(speeds, down, linewidth=2.2, color="#0f766e", label="Downforce")
    ax.set_title("Aerodynamic Forces from Simulator")
    ax.set_xlabel("Vehicle speed (m/s)")
    ax.set_ylabel("Force (N)")
    ax.grid(True, linestyle="--", alpha=0.35)
    ax.legend(loc="upper left")

    save_plot(fig, output_path)


def generate_cp_load_split_plot(vehicle, config: dict, output_path: str):
    speeds = np.linspace(6.0, 42.0, 120)
    wheelbase = max(float(vehicle.params.wheelbase), 1e-6)

    cp_front_bias = 0.35 * wheelbase
    cp_rear_bias = 0.75 * wheelbase
    cp_cases = [
        ("Front-biased CoP", cp_front_bias, "#0f766e"),
        ("Rear-biased CoP", cp_rear_bias, "#1d4ed8"),
    ]

    original_cp = float(vehicle.params.aero_centre_of_pressure)
    fig = plt.figure(figsize=(9.0, 5.5))
    ax = fig.add_subplot(111)

    for label, cp_value, color in cp_cases:
        vehicle.params.aero_centre_of_pressure = cp_value
        front_vals = []
        rear_vals = []
        for v in speeds:
            state = _compute_normal_loads_for_longitudinal(vehicle, v_car=float(v), a_long=0.0, config=config)
            front_vals.append(float(state["front_per_tyre"]))
            rear_vals.append(float(state["rear_per_tyre"]))

        ax.plot(speeds, front_vals, linewidth=2.0, color=color, linestyle="-", label=f"{label} front per tyre")
        ax.plot(speeds, rear_vals, linewidth=2.0, color=color, linestyle="--", label=f"{label} rear per tyre")

    vehicle.params.aero_centre_of_pressure = original_cp

    ax.set_title("Aero CoP Effect on Front and Rear Tyre Loads")
    ax.set_xlabel("Vehicle speed (m/s)")
    ax.set_ylabel("Normal load per tyre (N)")
    ax.grid(True, linestyle="--", alpha=0.35)
    ax.legend(fontsize=8, loc="lower right")

    save_plot(fig, output_path)


def generate_speed_profile_tradeoff_plot(config: dict, output_path: str):
    track = load_track(config["track"]["file_path"], debug_mode=False)

    baseline_vehicle = create_vehicle(config)
    baseline_result = run_lap_time_simulation(track, baseline_vehicle, config, display=False)

    aero_package_vehicle = create_vehicle(config)
    aero_package_vehicle.params.downforce_coefficient *= 1.45
    aero_package_vehicle.params.drag_coefficient *= 1.18
    aero_package_result = run_lap_time_simulation(track, aero_package_vehicle, config, display=False)

    distances = np.array([p.distance for p in track.points], dtype=float)
    delta_speed = np.asarray(aero_package_result.final_speeds) - np.asarray(baseline_result.final_speeds)

    sample_speed = 30.0
    baseline_drag = float(baseline_vehicle.compute_aero_drag(sample_speed))
    modified_drag = float(aero_package_vehicle.compute_aero_drag(sample_speed))
    baseline_downforce = float(baseline_vehicle.compute_downforce(sample_speed))
    modified_downforce = float(aero_package_vehicle.compute_downforce(sample_speed))

    faster_points = int((delta_speed > 0).sum())
    slower_points = int((delta_speed < 0).sum())
    equal_points = int((delta_speed == 0).sum())
    delta_lap = float(aero_package_result.lap_time - baseline_result.lap_time)
    delta_min = float(delta_speed.min())
    delta_max = float(delta_speed.max())

    fig = plt.figure(figsize=(10.0, 7.2))
    ax1 = fig.add_subplot(211)
    ax2 = fig.add_subplot(212, sharex=ax1)
    ax1.plot(distances, baseline_result.final_speeds, linewidth=1.8, color="#334155", label=f"Baseline lap {baseline_result.lap_time:.2f} s")
    ax1.plot(distances, aero_package_result.final_speeds, linewidth=1.8, color="#0f766e", label=f"Higher downforce and drag lap {aero_package_result.lap_time:.2f} s")
    ax1.set_title("Speed Profile Tradeoff from Aero Package Change")
    ax1.set_ylabel("Speed (m/s)")
    ax1.grid(True, linestyle="--", alpha=0.35)
    ax1.legend(loc="lower right")

    ax2.plot(distances, delta_speed, linewidth=1.8, color="#1d4ed8")
    ax2.axhline(0.0, color="#475569", linewidth=1.0, alpha=0.7)
    ax2.set_xlabel("Distance along track (m)")
    ax2.set_ylabel("Aero minus baseline (m/s)")
    ax2.grid(True, linestyle="--", alpha=0.35)

    save_plot(fig, output_path)

    return {
        "baseline_cl": float(baseline_vehicle.params.downforce_coefficient),
        "modified_cl": float(aero_package_vehicle.params.downforce_coefficient),
        "baseline_cd": float(baseline_vehicle.params.drag_coefficient),
        "modified_cd": float(aero_package_vehicle.params.drag_coefficient),
        "sample_speed_mps": sample_speed,
        "baseline_drag_n": baseline_drag,
        "modified_drag_n": modified_drag,
        "baseline_downforce_n": baseline_downforce,
        "modified_downforce_n": modified_downforce,
        "baseline_lap_s": float(baseline_result.lap_time),
        "modified_lap_s": float(aero_package_result.lap_time),
        "delta_lap_s": delta_lap,
        "faster_points": faster_points,
        "slower_points": slower_points,
        "equal_points": equal_points,
        "delta_min_mps": delta_min,
        "delta_max_mps": delta_max,
    }


def main():
    cfg = load_config(os.path.join(REPO_ROOT, "config.json"))
    cfg = with_b1_variant(cfg)
    vehicle = create_vehicle(cfg)

    out_dir = os.path.join(REPO_ROOT, "docs", "lessons", "figures", "aero_model_intro")

    p1 = os.path.join(out_dir, "aero_forces_vs_speed_from_sim.png")
    p2 = os.path.join(out_dir, "aero_cp_load_split_vs_speed_from_sim.png")
    p3 = os.path.join(out_dir, "aero_speed_profile_tradeoff_from_sim.png")

    generate_aero_forces_vs_speed(vehicle, p1)
    print(f"Saved plot: {p1}")

    generate_cp_load_split_plot(vehicle, cfg, p2)
    print(f"Saved plot: {p2}")

    metrics = generate_speed_profile_tradeoff_plot(cfg, p3)
    print(f"Saved plot: {p3}")

    print("Aero tradeoff metrics (baseline -> modified):")
    print(
        f"  Cl: {metrics['baseline_cl']:.4f} -> {metrics['modified_cl']:.4f} "
        f"({(metrics['modified_cl'] / max(metrics['baseline_cl'], 1e-12) - 1.0) * 100.0:+.1f}%)"
    )
    print(
        f"  Cd: {metrics['baseline_cd']:.4f} -> {metrics['modified_cd']:.4f} "
        f"({(metrics['modified_cd'] / max(metrics['baseline_cd'], 1e-12) - 1.0) * 100.0:+.1f}%)"
    )
    print(
        f"  Drag at {metrics['sample_speed_mps']:.0f} m/s: {metrics['baseline_drag_n']:.2f} N "
        f"-> {metrics['modified_drag_n']:.2f} N"
    )
    print(
        f"  Downforce at {metrics['sample_speed_mps']:.0f} m/s: {metrics['baseline_downforce_n']:.2f} N "
        f"-> {metrics['modified_downforce_n']:.2f} N"
    )
    print(
        f"  Lap time: {metrics['baseline_lap_s']:.3f} s -> {metrics['modified_lap_s']:.3f} s "
        f"(delta {metrics['delta_lap_s']:+.3f} s)"
    )
    print(
        f"  Speed profile points faster/slower/equal: "
        f"{metrics['faster_points']}/{metrics['slower_points']}/{metrics['equal_points']}"
    )


if __name__ == "__main__":
    main()
