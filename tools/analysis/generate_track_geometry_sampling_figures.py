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

from track.track import load_track


def load_config(config_path: str):
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_plot(fig, output_path: str):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def generate_track_map_figure(x, y, ds, output_path: str):
    idx_max = int(np.argmax(ds))
    idx_min = int(np.argmin(ds))

    fig = plt.figure(figsize=(8.4, 7.2))
    ax = fig.add_subplot(111)
    ax.plot(x, y, linewidth=1.2, color="#1f2937", alpha=0.9, label="Track centerline")
    ax.scatter(x, y, s=10, color="#2563eb", alpha=0.35, label="Sampled points")

    # Highlight largest and smallest segment spacing on the path.
    ax.plot(
        [x[idx_max], x[idx_max + 1]],
        [y[idx_max], y[idx_max + 1]],
        linewidth=3.0,
        color="#dc2626",
        label=f"Largest ds = {ds[idx_max]:.2f} m",
    )
    ax.plot(
        [x[idx_min], x[idx_min + 1]],
        [y[idx_min], y[idx_min + 1]],
        linewidth=3.0,
        color="#0f766e",
        label=f"Smallest ds = {ds[idx_min]:.2f} m",
    )

    ax.scatter(x[0], y[0], s=55, color="#16a34a", label="First point")
    ax.scatter(x[-1], y[-1], s=55, color="#7c3aed", label="Last point")

    ax.set_title("Track Centerline and Sampling Points")
    ax.set_xlabel("X (m)")
    ax.set_ylabel("Y (m)")
    ax.set_aspect("equal", "box")
    ax.grid(True, linestyle="--", alpha=0.35)
    ax.legend(loc="upper right", fontsize=8)

    save_plot(fig, output_path)


def generate_spacing_curvature_figure(distances, ds, curvature, output_path: str):
    mid_s = 0.5 * (distances[:-1] + distances[1:])

    fig = plt.figure(figsize=(11.2, 6.8))
    ax1 = fig.add_subplot(211)
    ax2 = fig.add_subplot(212, sharex=ax1)

    ax1.plot(mid_s, ds, linewidth=1.4, color="#0f766e")
    ax1.set_ylabel("Segment length ds (m)")
    ax1.set_title("Sampling Spacing and Curvature Along Track")
    ax1.grid(True, linestyle="--", alpha=0.35)

    ax2.plot(distances, curvature, linewidth=1.2, color="#2563eb", label="Signed curvature")
    ax2.plot(distances, np.abs(curvature), linewidth=1.2, color="#dc2626", alpha=0.8, label="Absolute curvature")
    ax2.axhline(0.0, color="#6b7280", linewidth=0.8)
    ax2.set_xlabel("Distance along track (m)")
    ax2.set_ylabel("Curvature (1/m)")
    ax2.grid(True, linestyle="--", alpha=0.35)
    ax2.legend(loc="upper right", fontsize=8)

    save_plot(fig, output_path)


def generate_ds_effect_g_figure(ds_values, output_path: str):
    v_prev = 20.0
    v_curr = 25.0
    g_values = [((v_curr ** 2 - v_prev ** 2) / (2.0 * ds)) / 9.81 for ds in ds_values]

    labels = [f"ds={ds:.2f} m" for ds in ds_values]

    fig = plt.figure(figsize=(8.4, 4.9))
    ax = fig.add_subplot(111)
    bars = ax.bar(labels, g_values, color=["#dc2626", "#2563eb", "#0f766e"])
    ax.set_title("Same Speed Change With Different Segment Length")
    ax.set_ylabel("Estimated longitudinal g")
    ax.grid(True, axis="y", linestyle="--", alpha=0.35)

    for bar, g_val in zip(bars, g_values):
        ax.text(
            bar.get_x() + bar.get_width() * 0.5,
            g_val + 0.02,
            f"{g_val:.2f} g",
            ha="center",
            va="bottom",
            fontsize=9,
        )

    ax.text(
        0.02,
        0.98,
        "Example uses v from 20 to 25 m/s\nFormula from lap integration loop",
        transform=ax.transAxes,
        ha="left",
        va="top",
        fontsize=8,
        bbox={"facecolor": "white", "alpha": 0.8, "edgecolor": "none"},
    )

    save_plot(fig, output_path)


def main():
    cfg = load_config(os.path.join(REPO_ROOT, "config.json"))
    track = load_track(cfg["track"]["file_path"], debug_mode=False)

    x = np.asarray([p.x for p in track.points], dtype=float)
    y = np.asarray([p.y for p in track.points], dtype=float)
    distances = np.asarray([p.distance for p in track.points], dtype=float)
    curvature = np.asarray([p.curvature for p in track.points], dtype=float)
    ds = np.diff(distances)

    out_dir = os.path.join(REPO_ROOT, "docs", "lessons", "figures", "track_geometry_sampling")
    map_fig = os.path.join(out_dir, "track_points_and_spacing_from_track.png")
    spacing_fig = os.path.join(out_dir, "sampling_spacing_and_curvature_from_track.png")
    ds_effect_fig = os.path.join(out_dir, "segment_length_effect_on_longitudinal_g.png")

    generate_track_map_figure(x, y, ds, map_fig)
    generate_spacing_curvature_figure(distances, ds, curvature, spacing_fig)

    ds_stats = {
        "min": float(np.min(ds)) if len(ds) else 0.0,
        "median": float(np.median(ds)) if len(ds) else 0.0,
        "max": float(np.max(ds)) if len(ds) else 0.0,
    }
    generate_ds_effect_g_figure(
        [ds_stats["min"], ds_stats["median"], ds_stats["max"]],
        ds_effect_fig,
    )

    closure_gap = float(np.sqrt((x[-1] - x[0]) ** 2 + (y[-1] - y[0]) ** 2))

    summary = {
        "track_path": cfg["track"]["file_path"],
        "point_count": int(len(track.points)),
        "total_length_m": float(track.total_length),
        "closure_gap_m": closure_gap,
        "segment_length_stats_m": ds_stats,
        "curvature_abs_max_1pm": float(np.max(np.abs(curvature))) if len(curvature) else 0.0,
        "figures": {
            "track_map": map_fig,
            "spacing_curvature": spacing_fig,
            "segment_length_effect": ds_effect_fig,
        },
    }

    print("Track geometry and sampling figure generation complete")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
