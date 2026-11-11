import json
import math
from pathlib import Path

from fastapi import HTTPException

from app.paths import config_path, parameters_path


def _load_base_config() -> dict:
    with open(config_path(), "r", encoding="utf-8") as f:
        return json.load(f)


def _load_base_parameters() -> dict:
    with open(parameters_path(), "r", encoding="utf-8") as f:
        data = json.load(f)
    data.pop("_comments", None)
    return data


def get_parameters() -> dict:
    return _load_base_parameters()


def get_config() -> dict:
    return _load_base_config()


def run_lap(parameters: dict | None = None, overrides=None) -> dict:
    from app.security.config_overrides import ConfigOverrides, build_config
    from simulator.simulator import run_lap_time_simulation
    from track.track import load_track
    from vehicle.vehicle import create_vehicle

    overrides = overrides if overrides is not None else ConfigOverrides()
    try:
        cfg = build_config(_load_base_config(), overrides)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    if parameters is not None:
        cfg["vehicle_parameters"] = parameters

    try:
        vehicle = create_vehicle(cfg)
    except KeyError as e:
        raise HTTPException(status_code=422, detail=f"Missing parameter: {e}")
    track = load_track(cfg["track"]["file_path"], cfg.get("debug_mode", False))
    result = run_lap_time_simulation(track, vehicle, cfg, display=False)

    distances_m = [float(p.distance) for p in track.points]
    x_m = [float(p.x) for p in track.points]
    y_m = [float(p.y) for p in track.points]
    curvature_1pm = [float(p.curvature) for p in track.points]
    speeds_kmh = [float(s) * 3.6 for s in result.final_speeds]
    g_lat = [0.0] + [float(g) for g in result.g_lat_channel]
    g_long = [0.0] + [float(g) for g in result.g_long_channel]

    base_mu = float(vehicle.params.base_mu) if vehicle.params.base_mu else 1.0
    mu_util = [math.hypot(g_lat[i], g_long[i]) / base_mu for i in range(len(g_lat))]

    g_const = 9.81
    m = float(vehicle.params.mass)
    h = float(vehicle.params.cog_z)
    L = max(float(vehicle.params.wheelbase), 1e-6)
    front_frac = min(max(float(vehicle.params.cog_longitudinal_pos), 0.0), 1.0)
    rear_frac = 1.0 - front_frac
    aero_cp = float(getattr(vehicle.params, "aero_centre_of_pressure", L * 0.5))
    aero_cp_clamped = min(max(aero_cp, 0.0), L)
    aero_front_frac = 1.0 - (aero_cp_clamped / L)
    static_front_axle = m * g_const * front_frac
    static_rear_axle  = m * g_const * rear_frac

    normal_load_front_n = []
    normal_load_rear_n = []
    for i in range(len(track.points)):
        v = float(result.final_speeds[i])
        a_long = float(g_long[i]) * g_const
        f_down = max(0.0, float(vehicle.compute_downforce(v)))
        aero_front = aero_front_frac * f_down
        aero_rear  = (1.0 - aero_front_frac) * f_down
        delta = (m * a_long * h) / L
        normal_load_front_n.append(max(0.0, static_front_axle + aero_front - delta))
        normal_load_rear_n.append( max(0.0, static_rear_axle  + aero_rear  + delta))

    max_abs_g_lat = max((abs(g) for g in g_lat), default=0.0)
    max_abs_g_long = max((abs(g) for g in g_long), default=0.0)

    return {
        "lap_time_s": float(result.lap_time),
        "track_file_path": Path(cfg["track"]["file_path"]).name,
        "points": int(len(track.points)),
        "max_abs_g_lat": max_abs_g_lat,
        "max_abs_g_long": max_abs_g_long,
        "base_mu": base_mu,
        "diagnostics": {
            "fallback_rate": float(result.diagnostics.get("fallback_rate", 0.0)),
            "corner_fallback_count": int(sum(1 for x in result.diagnostics.get("corner_fallback_used", []) if x)),
        },
        "telemetry": {
            "distances_m": distances_m,
            "x_m": x_m,
            "y_m": y_m,
            "speeds_kmh": speeds_kmh,
            "g_lat": g_lat,
            "g_long": g_long,
            "curvature_1pm": curvature_1pm,
            "normal_load_front_n": normal_load_front_n,
            "normal_load_rear_n": normal_load_rear_n,
            "mu_util": mu_util,
        },
    }


def metadata() -> dict:
    cfg = _load_base_config()
    params_json = _load_base_parameters()
    default_track = cfg.get("track", {}).get("file_path", "")

    return {
        "app_name": "LGR Sim Workbench",
        "model_scope": "Quasi-static lap-time simulator (production v1)",
        "deferred_parameters": ["suspension_stiffness", "damping_coefficient"],
        "track_default": Path(default_track).name if default_track else "",
        "parameter_file_sections": list(params_json.keys()),
    }
