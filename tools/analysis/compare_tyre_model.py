import argparse
import base64
import csv
import html
import json
import os
import sys
from collections import defaultdict

import numpy as np
import pandas as pd

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))
SRC_ROOT = os.path.join(REPO_ROOT, "src")
sys.path.insert(0, SRC_ROOT)

from vehicle.Tyres.baseTyre import LookupTableTyreModel


DEFAULT_LAT_CSV = os.path.join(
    SCRIPT_DIR,
    "..",
    "..",
    "datasets",
    "vehicle",
    "tyre_data",
    "Round_8_12_PSI_Lateral_Load_TyreData.csv",
)
DEFAULT_LONG_CSV = os.path.join(
    SCRIPT_DIR,
    "..",
    "..",
    "datasets",
    "vehicle",
    "tyre_data",
    "Round_6_12_PSI_Longit_Load_TyreData.csv",
)


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)


def configure_matplotlib_backend(visualise: bool):
    import matplotlib

    if visualise:
        try:
            matplotlib.use("TkAgg")
        except Exception:
            matplotlib.use("QtAgg")
    else:
        matplotlib.use("Agg")


def import_pyplot():
    import matplotlib.pyplot as plt

    return plt


def add_3d_projection(fig, position):
    return fig.add_subplot(position, projection="3d")


def _hex_to_rgb(hex_color):
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i : i + 2], 16) for i in (0, 2, 4))


def _rgb_to_hex(rgb):
    return "#" + "".join(f"{max(0, min(255, int(round(c)))):02x}" for c in rgb)


def lighten_hex(hex_color, amount=0.2):
    r, g, b = _hex_to_rgb(hex_color)
    return _rgb_to_hex((r + (255 - r) * amount, g + (255 - g) * amount, b + (255 - b) * amount))


def darken_hex(hex_color, amount=0.15):
    r, g, b = _hex_to_rgb(hex_color)
    return _rgb_to_hex((r * (1.0 - amount), g * (1.0 - amount), b * (1.0 - amount)))


REPORT_TITLE = "Tyre Model Verification Report"

PLOTLY_CDN = "https://cdn.plot.ly/plotly-2.32.0.min.js"

COLOR_PALETTE = [
    "#1f77b4",
    "#ff7f0e",
    "#2ca02c",
    "#d62728",
    "#9467bd",
    "#8c564b",
    "#e377c2",
    "#7f7f7f",
    "#bcbd22",
    "#17becf",
]


def rmse(y_true, y_pred):
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    return float(np.sqrt(np.mean((y_true - y_pred) ** 2)))


def mae(y_true, y_pred):
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    return float(np.mean(np.abs(y_true - y_pred)))


def peak_error(y_true, y_pred):
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    return float(np.max(np.abs(y_pred)) - np.max(np.abs(y_true)))


def percent_error(value, reference):
    reference = float(reference)
    if abs(reference) < 1e-9:
        return 0.0
    return float(100.0 * value / reference)


def image_to_data_uri(path):
    with open(path, "rb") as f:
        encoded = base64.b64encode(f.read()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def load_model(lat_path, long_path, model_variant="baseline"):
    full_lat_path = os.path.abspath(lat_path)
    full_long_path = os.path.abspath(long_path)
    tyre_data_lat = LookupTableTyreModel._parse_lateral_file(full_lat_path)
    tyre_data_long = LookupTableTyreModel._parse_longitudinal_file(full_long_path)
    return LookupTableTyreModel.from_config(
        {
            "file_path_lateral": lat_path,
            "file_path_longit": long_path,
            "type": "lookup",
            "base_mu": 1.0,
            "model_variant": model_variant,
        }
    ), tyre_data_lat, tyre_data_long


def _max_abs_predicted_force(model, channel, slip_values, normal_load):
    if channel == "lateral":
        preds = [model.get_lateral_force(slip, normal_load=normal_load) for slip in slip_values]
    else:
        preds = [model.get_longitudinal_force(slip, normal_load=normal_load) for slip in slip_values]
    if not preds:
        return 0.0
    return float(np.max(np.abs(np.asarray(preds, dtype=float))))


def run_high_load_extrapolation_checks(model, tyre_data_lat, tyre_data_long, max_ratio_threshold, probe_scale=1.5):
    rows = []

    lat_df = tyre_data_lat.dropna(subset=["Slip Angle [deg]", "Lateral Force [N]", "Normal Load [N]"]).copy()
    if not lat_df.empty:
        lat_loads = pd.to_numeric(lat_df["Normal Load [N]"], errors="coerce").dropna().to_numpy(dtype=float)
        max_load = float(np.max(lat_loads)) if len(lat_loads) else 0.0
        probe_load = max_load * float(probe_scale)
        observed_peak = float(np.max(np.abs(pd.to_numeric(lat_df["Lateral Force [N]"], errors="coerce").to_numpy(dtype=float))))
        slip_values = pd.to_numeric(lat_df["Slip Angle [deg]"], errors="coerce").dropna().to_numpy(dtype=float)
        predicted_peak = _max_abs_predicted_force(model, "lateral", slip_values, probe_load)
        ratio = 0.0 if observed_peak <= 1e-9 else float(predicted_peak / observed_peak)
        rows.append(
            {
                "channel": "lateral",
                "max_measured_load_N": max_load,
                "probe_load_N": probe_load,
                "measured_peak_N": observed_peak,
                "predicted_peak_at_probe_N": predicted_peak,
                "growth_ratio": ratio,
                "threshold": float(max_ratio_threshold),
                "status": "PASS" if ratio <= float(max_ratio_threshold) else "FAIL",
            }
        )

    long_df = tyre_data_long.dropna(subset=["Slip Ratio [%]", "Longitudinal Force [N]", "Normal Load [N]"]).copy()
    if not long_df.empty:
        long_loads = pd.to_numeric(long_df["Normal Load [N]"], errors="coerce").dropna().to_numpy(dtype=float)
        max_load = float(np.max(long_loads)) if len(long_loads) else 0.0
        probe_load = max_load * float(probe_scale)
        observed_peak = float(np.max(np.abs(pd.to_numeric(long_df["Longitudinal Force [N]"], errors="coerce").to_numpy(dtype=float))))
        slip_values = pd.to_numeric(long_df["Slip Ratio [%]"], errors="coerce").dropna().to_numpy(dtype=float)
        predicted_peak = _max_abs_predicted_force(model, "longitudinal", slip_values, probe_load)
        ratio = 0.0 if observed_peak <= 1e-9 else float(predicted_peak / observed_peak)
        rows.append(
            {
                "channel": "longitudinal",
                "max_measured_load_N": max_load,
                "probe_load_N": probe_load,
                "measured_peak_N": observed_peak,
                "predicted_peak_at_probe_N": predicted_peak,
                "growth_ratio": ratio,
                "threshold": float(max_ratio_threshold),
                "status": "PASS" if ratio <= float(max_ratio_threshold) else "FAIL",
            }
        )

    return rows


def evaluate_lateral(model, tyre_data_lat):
    rows = []
    grouped = tyre_data_lat.dropna(subset=["Slip Angle [deg]", "Lateral Force [N]", "Normal Load [N]"]).groupby("Normal Load [N]")
    for normal_load, group in grouped:
        slip = pd.to_numeric(group["Slip Angle [deg]"], errors="coerce").to_numpy(dtype=float)
        force_true = pd.to_numeric(group["Lateral Force [N]"], errors="coerce").to_numpy(dtype=float)
        valid = np.isfinite(slip) & np.isfinite(force_true)
        slip = slip[valid]
        force_true = force_true[valid]
        force_pred = np.array([model.get_lateral_force(sa, normal_load=normal_load) for sa in slip], dtype=float)

        rows.append(
            {
                "channel": "lateral",
                "normal_load_N": float(normal_load),
                "n_points": int(len(force_true)),
                "rmse_N": rmse(force_true, force_pred),
                "mae_N": mae(force_true, force_pred),
                "peak_error_N": peak_error(force_true, force_pred),
                "peak_true_N": float(np.max(np.abs(force_true))),
                "peak_pred_N": float(np.max(np.abs(force_pred))),
                "rmse_pct_of_peak": percent_error(rmse(force_true, force_pred), np.max(np.abs(force_true))),
                "mae_pct_of_peak": percent_error(mae(force_true, force_pred), np.max(np.abs(force_true))),
            }
        )
    return rows


def evaluate_longitudinal(model, tyre_data_long):
    rows = []
    grouped = tyre_data_long.dropna(subset=["Slip Ratio [%]", "Longitudinal Force [N]", "Normal Load [N]"]).groupby("Normal Load [N]")
    for normal_load, group in grouped:
        slip = pd.to_numeric(group["Slip Ratio [%]"], errors="coerce").to_numpy(dtype=float)
        force_true = pd.to_numeric(group["Longitudinal Force [N]"], errors="coerce").to_numpy(dtype=float)
        valid = np.isfinite(slip) & np.isfinite(force_true)
        slip = slip[valid]
        force_true = force_true[valid]
        force_pred = np.array([model.get_longitudinal_force(sr, normal_load=normal_load) for sr in slip], dtype=float)

        rows.append(
            {
                "channel": "longitudinal",
                "normal_load_N": float(normal_load),
                "n_points": int(len(force_true)),
                "rmse_N": rmse(force_true, force_pred),
                "mae_N": mae(force_true, force_pred),
                "peak_error_N": peak_error(force_true, force_pred),
                "peak_true_N": float(np.max(np.abs(force_true))),
                "peak_pred_N": float(np.max(np.abs(force_pred))),
                "rmse_pct_of_peak": percent_error(rmse(force_true, force_pred), np.max(np.abs(force_true))),
                "mae_pct_of_peak": percent_error(mae(force_true, force_pred), np.max(np.abs(force_true))),
            }
        )
    return rows


def plot_channel(output_path, title, model, group_rows, force_col, slip_col, get_force, xlabel, ylabel, close_after_save=True):
    plt = import_pyplot()
    fig = plt.figure(figsize=(12, 9))
    ax = fig.add_subplot(111)
    cmap = plt.get_cmap("tab10")

    for idx, (normal_load, group) in enumerate(group_rows):
        slip = pd.to_numeric(group[slip_col], errors="coerce").to_numpy(dtype=float)
        force_true = pd.to_numeric(group[force_col], errors="coerce").to_numpy(dtype=float)
        valid = np.isfinite(slip) & np.isfinite(force_true)
        slip = slip[valid]
        force_true = force_true[valid]
        force_pred = np.array([get_force(value, normal_load) for value in slip], dtype=float)
        base_color = COLOR_PALETTE[idx % len(COLOR_PALETTE)]
        ttc_color = lighten_hex(base_color, 0.18)
        model_color = darken_hex(base_color, 0.10)
        ax.plot(slip, force_true, "o", markersize=3, alpha=0.55, color=ttc_color, label=f"TTC {int(normal_load)} N")
        ax.plot(slip, force_pred, "-", linewidth=2.2, color=model_color, label=f"Model {int(normal_load)} N")

    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.grid(True, linestyle="--", alpha=0.3)
    ax.legend(fontsize=8, ncol=2)
    fig.tight_layout()
    fig.savefig(output_path, dpi=170)
    if close_after_save:
        plt.close(fig)


def plot_3d_channel(output_path, title, model, group_rows, force_col, slip_col, get_force, xlabel, ylabel="Normal Load (N)", zlabel="Force (N)", close_after_save=True):
    plt = import_pyplot()
    fig = plt.figure(figsize=(14, 10))
    ax = add_3d_projection(fig, 111)
    cmap = plt.get_cmap("tab10")

    for idx, (normal_load, group) in enumerate(group_rows):
        slip = pd.to_numeric(group[slip_col], errors="coerce").to_numpy(dtype=float)
        force_true = pd.to_numeric(group[force_col], errors="coerce").to_numpy(dtype=float)
        valid = np.isfinite(slip) & np.isfinite(force_true)
        slip = slip[valid]
        force_true = force_true[valid]
        force_pred = np.array([get_force(value, normal_load) for value in slip], dtype=float)
        base_color = COLOR_PALETTE[idx % len(COLOR_PALETTE)]
        ttc_color = lighten_hex(base_color, 0.18)
        model_color = darken_hex(base_color, 0.10)
        ax.plot(slip, [normal_load] * len(slip), force_true, "o", markersize=3, alpha=0.50, color=ttc_color, label=f"TTC {int(normal_load)} N")
        ax.plot(slip, [normal_load] * len(slip), force_pred, "-", linewidth=2.2, color=model_color, label=f"Model {int(normal_load)} N")

    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.set_zlabel(zlabel)
    ax.legend(fontsize=8, ncol=2)
    fig.tight_layout()
    fig.savefig(output_path, dpi=170)
    if close_after_save:
        plt.close(fig)


def run_zero_force_checks(model):
    vehicle_normal_load = 320.0 * 9.81 / 4.0
    zero_tol = 1e-6
    zero_tests = [
        ("Lateral force at 0 slip angle, 0 normal load", lambda: model.get_lateral_force(0, normal_load=0), True, zero_tol),
        ("Lateral force at 0 slip angle, 200N normal load", lambda: model.get_lateral_force(0, normal_load=200), True, zero_tol),
        (f"Lateral force at 0 slip angle, vehicle normal load ({vehicle_normal_load:.1f}N)", lambda: model.get_lateral_force(0, normal_load=vehicle_normal_load), True, zero_tol),
        ("Longitudinal force at 0 slip ratio, 0 normal load", lambda: model.get_longitudinal_force(0, normal_load=0), True, zero_tol),
        ("Longitudinal force at 0 slip ratio, 200N normal load", lambda: model.get_longitudinal_force(0, normal_load=200), True, zero_tol),
        (f"Longitudinal force at 0 slip ratio, vehicle normal load ({vehicle_normal_load:.1f}N)", lambda: model.get_longitudinal_force(0, normal_load=vehicle_normal_load), True, zero_tol),
        ("Lateral force at 10 deg slip angle, 0 normal load", lambda: model.get_lateral_force(10, normal_load=0), True, zero_tol),
        ("Longitudinal force at 10% slip ratio, 0 normal load", lambda: model.get_longitudinal_force(10, normal_load=0), True, zero_tol),
    ]

    lines = []
    rows = []
    for desc, func, expect_zero, tol in zero_tests:
        try:
            value = float(func())
            status = "OK"
            if expect_zero and abs(value) > tol:
                status = "FAIL"
            line = f"  {desc}: {value:.4f} [{status}]"
            rows.append({"description": desc, "value": value, "error": "", "status": status})
        except Exception as exc:
            line = f"  {desc}: ERROR {type(exc).__name__}: {exc}"
            rows.append({"description": desc, "value": None, "error": f"{type(exc).__name__}: {exc}", "status": "ERROR"})
        lines.append(line)
    return lines, rows


def build_plotly_3d_figure(group_rows, force_col, slip_col, get_force, title, xlabel, ylabel="Normal Load (N)", zlabel="Force (N)"):
    traces = []
    for idx, (normal_load, group) in enumerate(group_rows):
        slip = pd.to_numeric(group[slip_col], errors="coerce").to_numpy(dtype=float)
        force_true = pd.to_numeric(group[force_col], errors="coerce").to_numpy(dtype=float)
        valid = np.isfinite(slip) & np.isfinite(force_true)
        slip = slip[valid]
        force_true = force_true[valid]
        if len(slip) == 0:
            continue
        force_pred = np.array([get_force(value, normal_load) for value in slip], dtype=float)
        base_color = COLOR_PALETTE[idx % len(COLOR_PALETTE)]
        ttc_color = lighten_hex(base_color, 0.18)
        model_color = darken_hex(base_color, 0.10)
        traces.append(
            {
                "type": "scatter3d",
                "mode": "markers",
                "name": f"TTC {int(normal_load)} N",
                "x": slip.tolist(),
                "y": [float(normal_load)] * len(slip),
                "z": force_true.tolist(),
                "marker": {"size": 3, "opacity": 0.55, "color": ttc_color},
                "hovertemplate": "Slip=%{x:.3f}<br>Load=%{y:.0f} N<br>Force=%{z:.1f} N<extra>TTC</extra>",
            }
        )
        traces.append(
            {
                "type": "scatter3d",
                "mode": "lines",
                "name": f"Model {int(normal_load)} N",
                "x": slip.tolist(),
                "y": [float(normal_load)] * len(slip),
                "z": force_pred.tolist(),
                "line": {"width": 5, "color": model_color},
                "hovertemplate": "Slip=%{x:.3f}<br>Load=%{y:.0f} N<br>Force=%{z:.1f} N<extra>Model</extra>",
            }
        )

    layout = {
        "title": title,
        "scene": {
            "xaxis": {"title": xlabel},
            "yaxis": {"title": ylabel},
            "zaxis": {"title": zlabel},
            "camera": {
                "up": {"x": 0, "y": 0, "z": 1},
                "center": {"x": 0, "y": 0, "z": 0},
                "eye": {"x": -1.55, "y": -1.45, "z": 0.82},
            },
        },
        "legend": {"orientation": "h"},
        "margin": {"l": 0, "r": 0, "t": 50, "b": 0},
    }
    return {"div_id": title.lower().replace(" ", "_").replace(":", "").replace("/", "_"), "traces": traces, "layout": layout}


def dataframe_to_html(rows, float_columns=None):
    if not rows:
        return "<p>No data available.</p>"
    df = pd.DataFrame(rows)
    if float_columns:
        for col in float_columns:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.to_html(index=False, classes="table table-striped table-sm", border=0, escape=True)


def build_html_report(
    report_path,
    *,
    validation_passed,
    args,
    lateral_rmse_pct,
    longitudinal_rmse_pct,
    all_rows,
    zero_force_rows,
    extrapolation_rows,
    tyre_domain_rows,
    image_paths,
    plotly_figures,
    summary_csv,
):
    summary_rows = []
    for row in all_rows:
        summary_rows.append({
            "channel": row["channel"],
            "normal_load_N": row["normal_load_N"],
            "n_points": row["n_points"],
            "rmse_N": f"{row['rmse_N']:.1f}",
            "mae_N": f"{row['mae_N']:.1f}",
            "peak_error_N": f"{row['peak_error_N']:.1f}",
            "peak_true_N": f"{row['peak_true_N']:.1f}",
            "peak_pred_N": f"{row['peak_pred_N']:.1f}",
            "rmse_pct_of_peak": f"{row['rmse_pct_of_peak']:.2f}",
            "mae_pct_of_peak": f"{row['mae_pct_of_peak']:.2f}",
        })

    zero_rows = []
    for row in zero_force_rows:
        zero_rows.append({
            "check": row["description"],
            "status": row["status"],
            "value": "" if row["value"] is None else f"{row['value']:.4f}",
            "error": row["error"],
        })

    extrapolation_table_rows = []
    for row in extrapolation_rows:
        extrapolation_table_rows.append(
            {
                "channel": row["channel"],
                "max_measured_load_N": f"{row['max_measured_load_N']:.1f}",
                "probe_load_N": f"{row['probe_load_N']:.1f}",
                "measured_peak_N": f"{row['measured_peak_N']:.1f}",
                "predicted_peak_at_probe_N": f"{row['predicted_peak_at_probe_N']:.1f}",
                "growth_ratio": f"{row['growth_ratio']:.3f}",
                "threshold": f"{row['threshold']:.3f}",
                "status": row["status"],
            }
        )

    tyre_domain_table_rows = []
    for row in tyre_domain_rows:
        tyre_domain_table_rows.append(
            {
                "metric": row["metric"],
                "value": row["value"],
            }
        )

    image_cards = []
    for label, path in image_paths:
        image_cards.append(
            f"<div class='image-card'><h3>{html.escape(label)}</h3><img src='{image_to_data_uri(path)}' alt='{html.escape(label)}'></div>"
        )

    plotly_blocks = []
    for figure in plotly_figures:
        data_json = json.dumps(figure["traces"])
        layout_json = json.dumps(figure["layout"])
        plotly_blocks.append(
            f"""
            <div class='plotly-card'>
              <h3>{html.escape(figure['layout']['title'])}</h3>
              <div id='{figure['div_id']}' class='plotly-div'></div>
              <script>
                Plotly.newPlot('{figure['div_id']}', {data_json}, {layout_json}, {{responsive: true}});
              </script>
            </div>
            """
        )

    html_text = f"""<!DOCTYPE html>
<html lang='en'>
<head>
    <meta charset='utf-8'>
    <meta name='viewport' content='width=device-width, initial-scale=1'>
    <title>{REPORT_TITLE}</title>
    <script src='{PLOTLY_CDN}'></script>
    <style>
        :root {{
            --bg: #f7f8fb;
            --panel: #ffffff;
            --text: #1f2937;
            --muted: #6b7280;
            --accent: #1d4ed8;
            --border: #d1d5db;
            --good: #0f766e;
            --bad: #b91c1c;
        }}
        body {{ font-family: Arial, Helvetica, sans-serif; background: var(--bg); color: var(--text); margin: 0; padding: 24px; }}
        .container {{ max-width: 1600px; margin: 0 auto; }}
        .hero {{ background: linear-gradient(135deg, #fff, #eef2ff); border: 1px solid var(--border); border-radius: 18px; padding: 24px; margin-bottom: 20px; }}
        .grid {{ display: grid; gap: 18px; }}
        .summary-grid {{ grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); margin-top: 16px; }}
        .card {{ background: var(--panel); border: 1px solid var(--border); border-radius: 16px; padding: 18px; box-shadow: 0 6px 18px rgba(15,23,42,0.05); }}
        .metric {{ font-size: 2rem; font-weight: 700; margin-top: 6px; }}
        .metric small {{ font-size: 0.85rem; color: var(--muted); font-weight: 600; }}
        h1, h2, h3 {{ margin-top: 0; }}
        h1 {{ margin-bottom: 8px; }}
        .muted {{ color: var(--muted); }}
        .pass {{ color: var(--good); font-weight: 700; }}
        .fail {{ color: var(--bad); font-weight: 700; }}
        .table-wrap {{ overflow-x: auto; }}
        table {{ width: 100%; border-collapse: collapse; background: white; }}
        th, td {{ border-bottom: 1px solid var(--border); padding: 10px 12px; text-align: left; vertical-align: top; }}
        th {{ position: sticky; top: 0; background: #f9fafb; }}
        .section {{ margin-top: 22px; }}
        .image-grid {{ grid-template-columns: repeat(auto-fit, minmax(520px, 1fr)); }}
        .image-card img {{ width: 100%; height: auto; border: 1px solid var(--border); border-radius: 12px; background: white; }}
        .plotly-div {{ width: 100%; height: 750px; }}
        .plotly-card {{ min-height: 820px; }}
        .note {{ font-size: 0.95rem; color: var(--muted); }}
        code {{ background: #eef2ff; padding: 2px 5px; border-radius: 4px; }}
        .learn-box details {{ border: 1px solid var(--border); border-radius: 12px; background: #fbfcff; padding: 10px 14px; }}
        .learn-box summary {{ cursor: pointer; font-weight: 700; color: #1e3a8a; padding: 6px 0; }}
        .learn-box p {{ line-height: 1.6; }}
        .learn-box ul {{ margin-top: 6px; margin-bottom: 10px; }}
        .learn-box li {{ margin-bottom: 6px; }}
        .formula {{ background: #f1f5f9; border: 1px solid #cbd5e1; border-radius: 8px; padding: 10px 12px; font-family: Consolas, 'Courier New', monospace; overflow-x: auto; }}
    </style>
</head>
<body>
    <div class='container'>
        <div class='hero'>
            <h1>{REPORT_TITLE}</h1>
            <p class='muted'>This page compares measured TTC tyre data with the current tyre model used in the simulator.</p>
            <p class='muted'>How the model works: it reads TTC force data at each normal load, finds the peak force for that load, and then uses a fitted Magic Formula curve shape to map slip to force. The reported errors show how close the model curve is to TTC data at each load. The same checks are repeated for lateral force <strong>Fy</strong> and longitudinal force <strong>Fx</strong>.</p>
            <p class='muted'>Colour coding uses matching hues per load. TTC points are shown in a lighter shade, and model curves are shown in a darker shade.</p>
            <div class='grid summary-grid'>
                <div class='card'><div class='muted'>Validation</div><div class='metric {'pass' if validation_passed else 'fail'}'>{'PASS' if validation_passed else 'FAIL'}</div><small>RMSE threshold: {args.rmse_threshold_pct:.2f}% of peak</small></div>
                <div class='card'><div class='muted'>Lateral mean RMSE</div><div class='metric'>{lateral_rmse_pct:.2f}%</div><small>as a percent of peak force</small></div>
                <div class='card'><div class='muted'>Longitudinal mean RMSE</div><div class='metric'>{longitudinal_rmse_pct:.2f}%</div><small>as a percent of peak force</small></div>
                <div class='card'><div class='muted'>Model Variant</div><div class='metric'><small>{html.escape(args.model_variant)}</small></div><small>High-load growth max ratio: {args.max_high_load_growth_ratio:.2f}</small></div>
            </div>
        </div>

        <div class='section card learn-box'>
            <details>
                <summary>Tyre Model Learning Journey: from real tyre behavior to model force output</summary>
                <p>This section is a practical walkthrough for new team members. It starts with real tyre behavior and then shows how that behavior is approximated in our simulator model.</p>

                <h3>1) What a real tyre does at the contact patch</h3>
                <p>A tyre only makes force where rubber touches the road. That area is called the contact patch. The road pushes on the tyre, and the tyre pushes back with equal and opposite force. This force can be split into two in-plane directions:</p>
                <ul>
                    <li><strong>Longitudinal force Fx</strong>: forward and backward force. This is drive and braking force.</li>
                    <li><strong>Lateral force Fy</strong>: side force. This is cornering force.</li>
                </ul>
                <p>The vertical load Fz sets how much grip is available. More load usually means more absolute force, but not in a perfectly linear way.</p>

                <h3>2) Why we use a Pacejka style curve</h3>
                <p>Measured tyre force curves are smooth, nonlinear, and saturating. At low slip, force rises quickly. Near the limit, force growth slows and then plateaus. A Pacejka style curve represents that shape well with a compact equation, which is why it is widely used in vehicle dynamics.</p>
                <p>In this project, TTC data gives us measured force points, and a Magic Formula style shape is fitted so the simulator can return force continuously for any slip input.</p>

                <h3>3) Core formula and what each term means</h3>
                <p>The curve shape is represented with a standard Magic Formula form:</p>
                <div class='formula'>F(x) = D * sin( C * atan( B*x - E*(B*x - atan(B*x)) ) )</div>
                <ul>
                    <li><strong>x</strong>: slip input. Slip angle for Fy, slip ratio for Fx.</li>
                    <li><strong>D</strong>: peak force scale for the current load bin.</li>
                    <li><strong>B</strong>: initial slope control near zero slip.</li>
                    <li><strong>C</strong>: overall curve shape factor.</li>
                    <li><strong>E</strong>: curvature adjustment near the shoulder and peak region.</li>
                </ul>
                <p>We fit B, C, and E from TTC data. D is tied to measured peak force at each normal load so peak levels stay grounded in data.</p>

                <h3>4) Worked example from input to output force</h3>
                <p>Suppose the simulator asks for lateral force at Fz = 900 N and slip angle = 4 deg. The model path is:</p>
                <ul>
                    <li>Pick or interpolate the relevant load-dependent peak scale D from TTC data around 900 N.</li>
                    <li>Convert the slip input into the model input variable x used by that channel.</li>
                    <li>Evaluate the Magic Formula expression using fitted B, C, E and the load-scaled D.</li>
                    <li>Return Fy in newtons to the vehicle solver.</li>
                </ul>
                <p>The longitudinal channel works the same way, but with slip ratio input and Fx output.</p>

                <h3>5) How tyre forces act on the car</h3>
                <p>Fx and Fy act at each wheel contact patch and generate chassis accelerations through the suspension and vehicle geometry. These wheel forces also create moments at the vehicle level, such as yaw moments during cornering and braking balance effects.</p>

                <h3>6) Hysteresis in real tyres</h3>
                <p>Real rubber is viscoelastic. During loading and unloading, the force response can differ, creating hysteresis loops. This depends on temperature, frequency, carcass behavior, and compound effects. The current baseline model here is quasi-static and does not model full hysteresis loops explicitly. That is a trade-off for simplicity, speed, and stable sweeps.</p>

                <h3>7) Resultant force and why this report is split by Fx and Fy</h3>
                <p>The actual in-plane tyre force magnitude is the resultant:</p>
                <div class='formula'>F_resultant = sqrt(Fx^2 + Fy^2)</div>
                <p>That resultant is physically important, especially under combined slip. In this verification page we evaluate channels separately first, because it makes model errors easier to diagnose. If Fy fit degrades, we can see that directly without mixing it with Fx behavior. Combined-force behavior is then handled in the model logic after channel checks.</p>

                <h3>8) How to read the rest of this page</h3>
                <ul>
                    <li>Use the error table to spot load bins with higher mismatch.</li>
                    <li>Use 2D plots to compare local curve shape by load.</li>
                    <li>Use 3D plots to inspect how force surfaces move with load.</li>
                    <li>Remember: lighter points are TTC measurements, darker lines are model output.</li>
                </ul>
            </details>
        </div>

        <div class='section card'>
            <h2>Per-load Errors</h2>
            <div class='table-wrap'>{dataframe_to_html(summary_rows)}</div>
        </div>

        <div class='section card'>
            <h2>Zero-Force and Sanity Checks</h2>
            <div class='table-wrap'>{dataframe_to_html(zero_rows)}</div>
            <p class='note'>These checks verify that the model returns zero at zero slip and zero load, and that the old corner-case sanity probes still behave consistently.</p>
        </div>

        <div class='section card'>
            <h2>High-Load Extrapolation Checks</h2>
            <div class='table-wrap'>{dataframe_to_html(extrapolation_table_rows)}</div>
            <p class='note'>Probe load is 1.5x the highest measured TTC normal load. Growth ratio compares predicted peak force at probe load to measured peak force at known TTC loads.</p>
        </div>

        <div class='section card'>
            <h2>Tyre Validity-Domain Diagnostics</h2>
            <div class='table-wrap'>{dataframe_to_html(tyre_domain_table_rows)}</div>
            <p class='note'>Counts track slip/load requests outside the TTC-derived validity ranges observed by the runtime tyre model API.</p>
        </div>

        <div class='section card'>
            <h2>2D Plots</h2>
            <div class='grid image-grid'>
                {''.join(image_cards)}
            </div>
        </div>

        <div class='section card'>
            <h2>Interactive 3D Plots</h2>
            <p class='note'>You can rotate, zoom, and inspect each load sweep directly in the browser.</p>
            {''.join(plotly_blocks)}
        </div>
    </div>
</body>
</html>"""

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(html_text)


def main():
    parser = argparse.ArgumentParser(description="Compare the current tyre model against TTC-derived data.")
    parser.add_argument("--lateral-csv", default=DEFAULT_LAT_CSV, help="Path to parsed lateral TTC CSV")
    parser.add_argument("--longitudinal-csv", default=DEFAULT_LONG_CSV, help="Path to parsed longitudinal TTC CSV")
    parser.add_argument("--output-dir", default=os.path.join(REPO_ROOT, "artifacts", "tyre_validation"), help="Where to write plots and reports")
    parser.add_argument("--validate", action="store_true", help="Run pass/fail TTC verification against the current tyre model")
    parser.add_argument("--visualise", action="store_true", help="Generate the legacy TTC vs model visualisations")
    parser.add_argument("--rmse-threshold-pct", type=float, default=12.0, help="Fail validation if any load-bin RMSE exceeds this percent of peak force")
    parser.add_argument("--model-variant", default="baseline", help="Tyre model variant (e.g. baseline, tyre_peak_load_clamp)")
    parser.add_argument("--max-high-load-growth-ratio", type=float, default=1.35, help="Fail validation if predicted peak force at 1.5x max TTC load exceeds this ratio")
    parser.add_argument("--max-out-of-domain-count", type=int, default=-1, help="Fail validation if out-of-domain usage count exceeds this value (negative disables gate)")
    args = parser.parse_args()

    ensure_dir(args.output_dir)

    configure_matplotlib_backend(args.visualise)
    plt = import_pyplot()

    model, tyre_data_lat, tyre_data_long = load_model(args.lateral_csv, args.longitudinal_csv, model_variant=args.model_variant)
    if hasattr(model, "reset_domain_diagnostics"):
        model.reset_domain_diagnostics()

    lateral_rows = evaluate_lateral(model, tyre_data_lat)
    longitudinal_rows = evaluate_longitudinal(model, tyre_data_long)
    all_rows = lateral_rows + longitudinal_rows

    summary_csv = os.path.join(args.output_dir, "tyre_model_verification.csv")
    with open(summary_csv, "w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "channel",
                "normal_load_N",
                "n_points",
                "rmse_N",
                "mae_N",
                "peak_error_N",
                "peak_true_N",
                "peak_pred_N",
                "rmse_pct_of_peak",
                "mae_pct_of_peak",
            ],
        )
        writer.writeheader()
        writer.writerows(all_rows)

    lateral_groups = list(tyre_data_lat.dropna(subset=["Slip Angle [deg]", "Lateral Force [N]", "Normal Load [N]"]).groupby("Normal Load [N]"))
    longitudinal_groups = list(tyre_data_long.dropna(subset=["Slip Ratio [%]", "Longitudinal Force [N]", "Normal Load [N]"]).groupby("Normal Load [N]"))

    if args.visualise or not args.validate:
        plot_channel(
            output_path=os.path.join(args.output_dir, "lateral_model_vs_ttc.png"),
            title="Lateral (Fy): TTC vs Current Tyre Model",
            model=model,
            group_rows=lateral_groups,
            force_col="Lateral Force [N]",
            slip_col="Slip Angle [deg]",
            get_force=lambda slip, normal_load: model.get_lateral_force(slip, normal_load=normal_load),
            xlabel="Slip Angle (deg)",
            ylabel="Lateral Force Fy (N)",
            close_after_save=True,
        )
        plot_3d_channel(
            output_path=os.path.join(args.output_dir, "lateral_model_vs_ttc_3d.png"),
            title="Lateral (Fy): TTC vs Current Tyre Model",
            model=model,
            group_rows=lateral_groups,
            force_col="Lateral Force [N]",
            slip_col="Slip Angle [deg]",
            get_force=lambda slip, normal_load: model.get_lateral_force(slip, normal_load=normal_load),
            xlabel="Slip Angle (deg)",
            zlabel="Lateral Force Fy (N)",
            close_after_save=True,
        )
        plot_channel(
            output_path=os.path.join(args.output_dir, "longitudinal_model_vs_ttc.png"),
            title="Longitudinal (Fx): TTC vs Current Tyre Model",
            model=model,
            group_rows=longitudinal_groups,
            force_col="Longitudinal Force [N]",
            slip_col="Slip Ratio [%]",
            get_force=lambda slip, normal_load: model.get_longitudinal_force(slip, normal_load=normal_load),
            xlabel="Slip Ratio (dataset units)",
            ylabel="Longitudinal Force Fx (N)",
            close_after_save=True,
        )
        plot_3d_channel(
            output_path=os.path.join(args.output_dir, "longitudinal_model_vs_ttc_3d.png"),
            title="Longitudinal (Fx): TTC vs Current Tyre Model",
            model=model,
            group_rows=longitudinal_groups,
            force_col="Longitudinal Force [N]",
            slip_col="Slip Ratio [%]",
            get_force=lambda slip, normal_load: model.get_longitudinal_force(slip, normal_load=normal_load),
            xlabel="Slip Ratio (dataset units)",
            zlabel="Longitudinal Force Fx (N)",
            close_after_save=True,
        )

    lateral_rmse_pct = float(np.mean([row["rmse_pct_of_peak"] for row in lateral_rows])) if lateral_rows else 0.0
    longitudinal_rmse_pct = float(np.mean([row["rmse_pct_of_peak"] for row in longitudinal_rows])) if longitudinal_rows else 0.0

    failed_rows = [
        row for row in all_rows if float(row["rmse_pct_of_peak"]) > float(args.rmse_threshold_pct)
    ]
    extrapolation_rows = run_high_load_extrapolation_checks(
        model,
        tyre_data_lat,
        tyre_data_long,
        max_ratio_threshold=args.max_high_load_growth_ratio,
        probe_scale=1.5,
    )
    tyre_domain_diag = model.get_domain_diagnostics() if hasattr(model, "get_domain_diagnostics") else {}
    tyre_domain_rows = [{"metric": k, "value": v} for k, v in tyre_domain_diag.items()]

    extrapolation_fail_rows = [row for row in extrapolation_rows if row["status"] != "PASS"]
    out_of_domain_total = int(tyre_domain_diag.get("out_of_domain_total", 0)) if isinstance(tyre_domain_diag, dict) else 0
    out_of_domain_gate_enabled = int(args.max_out_of_domain_count) >= 0
    out_of_domain_gate_pass = (out_of_domain_total <= int(args.max_out_of_domain_count)) if out_of_domain_gate_enabled else True
    validation_passed = (len(failed_rows) == 0) and (len(extrapolation_fail_rows) == 0) and out_of_domain_gate_pass

    html_report = os.path.join(args.output_dir, "tyre_model_verification.html")
    zero_force_lines, zero_force_rows = run_zero_force_checks(model)

    image_paths = [
        ("Lateral 2D Plot", os.path.join(args.output_dir, "lateral_model_vs_ttc.png")),
        ("Longitudinal 2D Plot", os.path.join(args.output_dir, "longitudinal_model_vs_ttc.png")),
    ]

    plotly_figures = [
        build_plotly_3d_figure(
            lateral_groups,
            force_col="Lateral Force [N]",
            slip_col="Slip Angle [deg]",
            get_force=lambda slip, normal_load: model.get_lateral_force(slip, normal_load=normal_load),
            title="Lateral (Fy): TTC vs Current Tyre Model",
            xlabel="Slip Angle (deg)",
            zlabel="Lateral Force Fy (N)",
        ),
        build_plotly_3d_figure(
            longitudinal_groups,
            force_col="Longitudinal Force [N]",
            slip_col="Slip Ratio [%]",
            get_force=lambda slip, normal_load: model.get_longitudinal_force(slip, normal_load=normal_load),
            title="Longitudinal (Fx): TTC vs Current Tyre Model",
            xlabel="Slip Ratio (dataset units)",
            zlabel="Longitudinal Force Fx (N)",
        ),
    ]

    build_html_report(
        html_report,
        validation_passed=validation_passed,
        args=args,
        lateral_rmse_pct=lateral_rmse_pct,
        longitudinal_rmse_pct=longitudinal_rmse_pct,
        all_rows=all_rows,
        zero_force_rows=zero_force_rows,
        extrapolation_rows=extrapolation_rows,
        tyre_domain_rows=tyre_domain_rows,
        image_paths=image_paths,
        plotly_figures=plotly_figures,
        summary_csv=summary_csv,
    )

    print("Tyre verification complete")
    print(f"Summary CSV: {summary_csv}")
    print(f"HTML Report: {html_report}")
    print(f"Lateral mean RMSE % peak: {lateral_rmse_pct:.2f}%")
    print(f"Longitudinal mean RMSE % peak: {longitudinal_rmse_pct:.2f}%")
    print(f"Validation threshold: {args.rmse_threshold_pct:.2f}% of peak")
    print(f"High-load growth ratio threshold: {args.max_high_load_growth_ratio:.2f}")
    print(f"Out-of-domain gate: {'disabled' if not out_of_domain_gate_enabled else f'<= {int(args.max_out_of_domain_count)}'}")
    print(f"Out-of-domain total count: {out_of_domain_total}")
    print(f"Model variant: {args.model_variant}")
    print(f"Validation result: {'PASS' if validation_passed else 'FAIL'}")

    if args.visualise:
        print("\n[INFO] Zero-Zero Test Results:")
        for line in zero_force_lines:
            print(line)

    if args.validate and not validation_passed:
        print("Failed rows:")
        for row in failed_rows:
            print(
                f"  {row['channel']} @ {row['normal_load_N']:.0f} N: RMSE%peak={row['rmse_pct_of_peak']:.2f}%"
            )
        for row in extrapolation_fail_rows:
            print(
                f"  {row['channel']} high-load growth ratio={row['growth_ratio']:.3f} (threshold={row['threshold']:.3f})"
            )
        if not out_of_domain_gate_pass:
            print(
                f"  out_of_domain_total={out_of_domain_total} exceeds threshold={int(args.max_out_of_domain_count)}"
            )
        raise SystemExit(1)


if __name__ == "__main__":
    main()