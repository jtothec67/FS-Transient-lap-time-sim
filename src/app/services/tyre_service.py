import numpy as np
import pandas as pd
from fastapi import HTTPException

from app.security.dataset_registry import get_tyre_lateral_path, get_tyre_longitudinal_path

_COLOR_PALETTE = [
    "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
    "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf",
]


def _lighten(hex_color: str, amount: float = 0.18) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return "#{:02x}{:02x}{:02x}".format(
        int(r + (255 - r) * amount),
        int(g + (255 - g) * amount),
        int(b + (255 - b) * amount),
    )


def _darken(hex_color: str, amount: float = 0.10) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return "#{:02x}{:02x}{:02x}".format(
        int(r * (1.0 - amount)),
        int(g * (1.0 - amount)),
        int(b * (1.0 - amount)),
    )


def _rmse(y_true, y_pred) -> float:
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    return float(np.sqrt(np.mean((y_true - y_pred) ** 2)))


def _mae(y_true, y_pred) -> float:
    return float(np.mean(np.abs(np.asarray(y_true, dtype=float) - np.asarray(y_pred, dtype=float))))


def _peak_error(y_true, y_pred) -> float:
    return float(np.max(np.abs(np.asarray(y_pred, dtype=float))) - np.max(np.abs(np.asarray(y_true, dtype=float))))


def _pct(value, reference) -> float:
    ref = float(reference)
    return 0.0 if abs(ref) < 1e-9 else float(100.0 * value / ref)


def _evaluate_lateral(model, df: pd.DataFrame) -> list[dict]:
    rows = []
    grouped = df.dropna(subset=["Slip Angle [deg]", "Lateral Force [N]", "Normal Load [N]"]).groupby("Normal Load [N]")
    for normal_load, group in grouped:
        slip = pd.to_numeric(group["Slip Angle [deg]"], errors="coerce").to_numpy(dtype=float)
        force_true = pd.to_numeric(group["Lateral Force [N]"], errors="coerce").to_numpy(dtype=float)
        valid = np.isfinite(slip) & np.isfinite(force_true)
        slip, force_true = slip[valid], force_true[valid]
        force_pred = np.array([model.get_lateral_force(sa, normal_load=normal_load) for sa in slip], dtype=float)
        peak = float(np.max(np.abs(force_true)))
        rows.append({
            "channel": "lateral",
            "normal_load_N": float(normal_load),
            "n_points": int(len(force_true)),
            "rmse_N": round(_rmse(force_true, force_pred), 2),
            "mae_N": round(_mae(force_true, force_pred), 2),
            "peak_error_N": round(_peak_error(force_true, force_pred), 2),
            "peak_true_N": round(peak, 2),
            "peak_pred_N": round(float(np.max(np.abs(force_pred))), 2),
            "rmse_pct_of_peak": round(_pct(_rmse(force_true, force_pred), peak), 3),
            "mae_pct_of_peak": round(_pct(_mae(force_true, force_pred), peak), 3),
        })
    return rows


def _evaluate_longitudinal(model, df: pd.DataFrame) -> list[dict]:
    rows = []
    grouped = df.dropna(subset=["Slip Ratio [%]", "Longitudinal Force [N]", "Normal Load [N]"]).groupby("Normal Load [N]")
    for normal_load, group in grouped:
        slip = pd.to_numeric(group["Slip Ratio [%]"], errors="coerce").to_numpy(dtype=float)
        force_true = pd.to_numeric(group["Longitudinal Force [N]"], errors="coerce").to_numpy(dtype=float)
        valid = np.isfinite(slip) & np.isfinite(force_true)
        slip, force_true = slip[valid], force_true[valid]
        force_pred = np.array([model.get_longitudinal_force(sr, normal_load=normal_load) for sr in slip], dtype=float)
        peak = float(np.max(np.abs(force_true)))
        rows.append({
            "channel": "longitudinal",
            "normal_load_N": float(normal_load),
            "n_points": int(len(force_true)),
            "rmse_N": round(_rmse(force_true, force_pred), 2),
            "mae_N": round(_mae(force_true, force_pred), 2),
            "peak_error_N": round(_peak_error(force_true, force_pred), 2),
            "peak_true_N": round(peak, 2),
            "peak_pred_N": round(float(np.max(np.abs(force_pred))), 2),
            "rmse_pct_of_peak": round(_pct(_rmse(force_true, force_pred), peak), 3),
            "mae_pct_of_peak": round(_pct(_mae(force_true, force_pred), peak), 3),
        })
    return rows


def _build_chart_series(model, df: pd.DataFrame, channel: str, max_ttc: int = 150, model_pts: int = 80) -> dict:
    ttc_datasets = []
    model_datasets = []

    if channel == "lateral":
        slip_col, force_col = "Slip Angle [deg]", "Lateral Force [N]"
        get_force = lambda s, fz: model.get_lateral_force(s, normal_load=fz)
        groups = df.dropna(subset=[slip_col, force_col, "Normal Load [N]"]).groupby("Normal Load [N]")
    else:
        slip_col, force_col = "Slip Ratio [%]", "Longitudinal Force [N]"
        get_force = lambda s, fz: model.get_longitudinal_force(s, normal_load=fz)
        groups = df.dropna(subset=[slip_col, force_col, "Normal Load [N]"]).groupby("Normal Load [N]")

    for idx, (normal_load, group) in enumerate(groups):
        slip = pd.to_numeric(group[slip_col], errors="coerce").to_numpy(dtype=float)
        force = pd.to_numeric(group[force_col], errors="coerce").to_numpy(dtype=float)
        valid = np.isfinite(slip) & np.isfinite(force)
        slip, force = slip[valid], force[valid]
        if len(slip) == 0:
            continue

        # Downsample TTC
        if len(slip) > max_ttc:
            idx_ds = np.round(np.linspace(0, len(slip) - 1, max_ttc)).astype(int)
            slip_ds, force_ds = slip[idx_ds], force[idx_ds]
        else:
            slip_ds, force_ds = slip, force

        # Model curve at even slip steps
        slip_model = np.linspace(float(slip.min()), float(slip.max()), model_pts)
        force_model = [float(get_force(s, normal_load)) for s in slip_model]

        base_color = _COLOR_PALETTE[idx % len(_COLOR_PALETTE)]
        ttc_datasets.append({
            "label": f"TTC {int(normal_load)} N",
            "color": _lighten(base_color, 0.18),
            "points": [{"x": round(float(s), 4), "y": round(float(f), 2)} for s, f in zip(slip_ds, force_ds)],
        })
        model_datasets.append({
            "label": f"Model {int(normal_load)} N",
            "color": _darken(base_color, 0.10),
            "points": [{"x": round(float(s), 4), "y": round(float(f), 2)} for s, f in zip(slip_model, force_model)],
        })

    return {"ttc": ttc_datasets, "model": model_datasets}


def _zero_force_checks(model) -> list[dict]:
    fz_vehicle = 320.0 * 9.81 / 4.0
    tests = [
        ("Fy at 0 slip, 0 N load",       lambda: model.get_lateral_force(0, normal_load=0),       True),
        ("Fy at 0 slip, 200 N load",      lambda: model.get_lateral_force(0, normal_load=200),     True),
        (f"Fy at 0 slip, {fz_vehicle:.0f} N load", lambda: model.get_lateral_force(0, normal_load=fz_vehicle), True),
        ("Fx at 0 slip, 0 N load",        lambda: model.get_longitudinal_force(0, normal_load=0),  True),
        ("Fx at 0 slip, 200 N load",      lambda: model.get_longitudinal_force(0, normal_load=200), True),
        (f"Fx at 0 slip, {fz_vehicle:.0f} N load", lambda: model.get_longitudinal_force(0, normal_load=fz_vehicle), True),
    ]
    rows = []
    for desc, fn, expect_zero in tests:
        try:
            val = float(fn())
            status = "FAIL" if expect_zero and abs(val) > 1e-6 else "OK"
            rows.append({"check": desc, "value": round(val, 4), "status": status, "error": ""})
        except Exception as exc:
            rows.append({"check": desc, "value": None, "status": "ERROR", "error": str(exc)})
    return rows


def _extrapolation_checks(model, df_lat, df_long, max_ratio: float = 1.35) -> list[dict]:
    rows = []
    for channel, df, slip_col, force_col, get_force in [
        ("lateral",      df_lat,  "Slip Angle [deg]",  "Lateral Force [N]",      lambda s, fz: model.get_lateral_force(s, normal_load=fz)),
        ("longitudinal", df_long, "Slip Ratio [%]",    "Longitudinal Force [N]", lambda s, fz: model.get_longitudinal_force(s, normal_load=fz)),
    ]:
        sub = df.dropna(subset=[slip_col, force_col, "Normal Load [N]"])
        if sub.empty:
            continue
        loads = pd.to_numeric(sub["Normal Load [N]"], errors="coerce").dropna().to_numpy(dtype=float)
        max_load = float(np.max(loads))
        probe_load = max_load * 1.5
        obs_peak = float(np.max(np.abs(pd.to_numeric(sub[force_col], errors="coerce").to_numpy(dtype=float))))
        slips = pd.to_numeric(sub[slip_col], errors="coerce").dropna().to_numpy(dtype=float)
        pred_peak = float(np.max(np.abs([get_force(s, probe_load) for s in slips[:80]])))
        ratio = 0.0 if obs_peak <= 1e-9 else pred_peak / obs_peak
        rows.append({
            "channel": channel,
            "max_measured_load_N": round(max_load, 1),
            "probe_load_N": round(probe_load, 1),
            "measured_peak_N": round(obs_peak, 1),
            "predicted_peak_at_probe_N": round(pred_peak, 1),
            "growth_ratio": round(ratio, 3),
            "threshold": round(max_ratio, 3),
            "status": "PASS" if ratio <= max_ratio else "FAIL",
        })
    return rows


def run_tyre_verify(
    lat_dataset: str,
    long_dataset: str,
    model_variant: str = "tyre_peak_load_clamp",
    rmse_threshold_pct: float = 12.0,
    base_mu: float = 1.0,
    mu_multiplier: float | None = None,
) -> dict:
    from vehicle.Tyres.baseTyre import LookupTableTyreModel

    try:
        full_lat  = str(get_tyre_lateral_path(lat_dataset))
        full_long = str(get_tyre_longitudinal_path(long_dataset))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    try:
        model = LookupTableTyreModel.from_config({
            "file_path_lateral": full_lat,
            "file_path_longit":  full_long,
            "type": "lookup",
            "base_mu": float(base_mu),
            "model_variant": model_variant,
        })
        df_lat  = LookupTableTyreModel._parse_lateral_file(full_lat)
        df_long = LookupTableTyreModel._parse_longitudinal_file(full_long)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Could not load tyre data: {exc}")

    lat_ref_mu  = float(getattr(model, "_lat_mu_reference",  1.0))
    long_ref_mu = float(getattr(model, "_long_mu_reference", 1.0))

    if mu_multiplier is not None:
        native = (lat_ref_mu + long_ref_mu) / 2.0
        effective_base_mu = float(native) * float(mu_multiplier)
        model.base_mu = effective_base_mu
    else:
        effective_base_mu = float(base_mu)

    lat_rows  = _evaluate_lateral(model, df_lat)
    long_rows = _evaluate_longitudinal(model, df_long)
    all_rows  = lat_rows + long_rows

    lat_rmse_pct  = float(np.mean([r["rmse_pct_of_peak"] for r in lat_rows]))  if lat_rows  else 0.0
    long_rmse_pct = float(np.mean([r["rmse_pct_of_peak"] for r in long_rows])) if long_rows else 0.0

    failed = [r for r in all_rows if r["rmse_pct_of_peak"] > rmse_threshold_pct]
    extrap = _extrapolation_checks(model, df_lat, df_long, max_ratio=1.35)
    extrap_failed = [r for r in extrap if r["status"] != "PASS"]
    validation_passed = len(failed) == 0 and len(extrap_failed) == 0

    lat_chart  = _build_chart_series(model, df_lat,  "lateral")
    long_chart = _build_chart_series(model, df_long, "longitudinal")

    return {
        "validation_passed": validation_passed,
        "lateral_rmse_pct":  round(lat_rmse_pct,  2),
        "longitudinal_rmse_pct": round(long_rmse_pct, 2),
        "rmse_threshold_pct": rmse_threshold_pct,
        "model_variant": model_variant,
        "base_mu": float(effective_base_mu),
        "mu_multiplier": None if mu_multiplier is None else float(mu_multiplier),
        "lat_ref_mu":  round(lat_ref_mu,  3),
        "long_ref_mu": round(long_ref_mu, 3),
        "lat_dataset": lat_dataset,
        "long_dataset": long_dataset,
        "rows": all_rows,
        "zero_force_rows": _zero_force_checks(model),
        "extrapolation_rows": extrap,
        "lateral_chart":  lat_chart,
        "longitudinal_chart": long_chart,
    }
