import json
import os
import sys

import matplotlib.pyplot as plt
import numpy as np


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))
SRC_ROOT = os.path.join(REPO_ROOT, "src")
if SRC_ROOT not in sys.path:
    sys.path.insert(0, SRC_ROOT)

from vehicle.vehicle import create_vehicle


def build_vehicle(config_path: str):
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    return create_vehicle(config)


def generate_fy_vs_slip_angle_plot(vehicle, output_path: str, normal_load_n: float = 900.0):
    # Plot a pure-slip slice at representative per-tyre load to show nonlinearity clearly.
    slip_values = np.linspace(-14.0, 14.0, 141)
    fy_values = [vehicle.tyre_model.get_lateral_force(float(sa), normal_load=float(normal_load_n)) for sa in slip_values]

    fig = plt.figure(figsize=(9, 5.5))
    ax = fig.add_subplot(111)
    ax.plot(slip_values, fy_values, color="#0f766e", linewidth=2.2, label=f"Fy at normal load = {normal_load_n:.0f} N")
    ax.scatter(slip_values[::10], np.asarray(fy_values)[::10], color="#0f766e", s=18, alpha=0.8)

    ax.set_title("Tyre Model Output from Simulator")
    ax.set_xlabel("Slip angle (deg)")
    ax.set_ylabel("Predicted lateral force Fy (N)")
    ax.axhline(0.0, color="#475569", linewidth=1.0, alpha=0.6)
    ax.axvline(0.0, color="#475569", linewidth=1.0, alpha=0.6)
    ax.grid(True, linestyle="--", alpha=0.35)
    ax.legend()
    fig.tight_layout()

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def generate_fx_vs_slip_ratio_plot(vehicle, output_path: str, normal_load_n: float = 900.0):
    # Respect the tyre model's expected slip-ratio units so the plot matches runtime behavior.
    ratio_like = bool(getattr(vehicle.tyre_model, "_longitudinal_slip_data_is_ratio", True))
    if ratio_like:
        slip_input = np.linspace(-0.22, 0.22, 181)
        slip_display = slip_input * 100.0
    else:
        slip_input = np.linspace(-22.0, 22.0, 181)
        slip_display = slip_input

    fx_values = [
        vehicle.tyre_model.get_longitudinal_force(float(sr), normal_load=float(normal_load_n))
        for sr in slip_input
    ]

    fig = plt.figure(figsize=(9, 5.5))
    ax = fig.add_subplot(111)
    ax.plot(slip_display, fx_values, color="#1d4ed8", linewidth=2.2, label=f"Fx at normal load = {normal_load_n:.0f} N")
    ax.scatter(slip_display[::12], np.asarray(fx_values)[::12], color="#1d4ed8", s=18, alpha=0.8)

    ax.set_title("Tyre Model Output from Simulator")
    ax.set_xlabel("Slip ratio (%)")
    ax.set_ylabel("Predicted longitudinal force Fx (N)")
    ax.axhline(0.0, color="#475569", linewidth=1.0, alpha=0.6)
    ax.axvline(0.0, color="#475569", linewidth=1.0, alpha=0.6)
    ax.grid(True, linestyle="--", alpha=0.35)
    ax.legend()
    fig.tight_layout()

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def main():
    config_path = os.path.join(REPO_ROOT, "config.json")
    fy_output_path = os.path.join(
        REPO_ROOT,
        "docs",
        "lessons",
        "figures",
        "tyre_model_intro",
        "fy_vs_slip_angle_from_sim.png",
    )
    fx_output_path = os.path.join(
        REPO_ROOT,
        "docs",
        "lessons",
        "figures",
        "tyre_model_intro",
        "fx_vs_slip_ratio_from_sim.png",
    )

    vehicle = build_vehicle(config_path)
    generate_fy_vs_slip_angle_plot(vehicle, output_path=fy_output_path, normal_load_n=900.0)
    print(f"Saved plot: {fy_output_path}")
    generate_fx_vs_slip_ratio_plot(vehicle, output_path=fx_output_path, normal_load_n=900.0)
    print(f"Saved plot: {fx_output_path}")


if __name__ == "__main__":
    main()
