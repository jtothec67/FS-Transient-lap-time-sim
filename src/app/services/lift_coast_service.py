import copy
import json

import numpy as np

from app.paths import config_path


def _load_base_config() -> dict:
    with open(config_path(), "r", encoding="utf-8") as f:
        return json.load(f)


def _run_single(vehicle, power_limit_kw: float, energy_target_kwh: float, dt: float) -> dict:
    v = 0.0
    dist = 0.0
    time_s = 0.0
    energy_used_kwh = 0.0
    launch_rpm = 4000.0
    coasting = False

    log = {
        "time": [],
        "distance": [],
        "velocity_kph": [],
        "power_in_kw": [],
        "energy_used_kwh": [],
    }

    for _ in range(300000):
        v_calc = max(v, 0.1)

        if energy_used_kwh >= energy_target_kwh:
            coasting = True

        gear = vehicle.select_optimal_gear(v_calc)
        wheel_rpm = vehicle.speed_to_rpm(v_calc, gear)
        engine_rpm = max(wheel_rpm, launch_rpm)
        max_engine_torque = vehicle.power_unit.get_torque(engine_rpm, throttle=1.0)
        max_engine_power_kw = vehicle.power_unit.getPower(engine_rpm, throttle=1.0)

        total_ratio = gear * vehicle.params.final_drive_ratio

        if not coasting:
            target_engine_power_kw = min(max_engine_power_kw, float(power_limit_kw))
            engine_omega = engine_rpm * 2.0 * np.pi / 60.0
            target_engine_torque = (target_engine_power_kw * 1000.0) / max(engine_omega, 1e-6)
            actual_engine_torque = min(target_engine_torque, max_engine_torque)
            wheel_torque = actual_engine_torque * total_ratio * vehicle.params.transmission_efficiency

            efficiency_pct = vehicle.power_unit.getEfficiency(engine_rpm, actual_engine_torque / max(max_engine_torque, 1e-6))
            if efficiency_pct <= 1.0:
                efficiency_pct = 30.0

            engine_power_out_kw = (actual_engine_torque * engine_omega) / 1000.0
            power_in_kw = engine_power_out_kw / (efficiency_pct / 100.0)
            energy_used_kwh += power_in_kw * (dt / 3600.0)
        else:
            wheel_torque = 0.0
            power_in_kw = 0.0

        f_tractive = wheel_torque / max(vehicle.params.wheel_radius, 1e-6)

        # cog_longitudinal_pos is the front mass fraction. Rear share is the complement.
        weight_rear = vehicle.params.mass * 9.81 * (1.0 - vehicle.params.cog_longitudinal_pos)
        f_downforce = vehicle.compute_downforce(v_calc)
        f_aero_rear = f_downforce * (vehicle.params.aero_centre_of_pressure / max(vehicle.params.wheelbase, 1e-6))
        normal_load_rear = weight_rear + f_aero_rear
        f_traction_limit = normal_load_rear * 1.5
        f_tractive = min(f_tractive, f_traction_limit)

        f_drag = vehicle.compute_aero_drag(v_calc)
        f_rolling = vehicle.params.mass * 9.81 * 0.015
        f_net = f_tractive - f_drag - f_rolling
        accel = f_net / max(vehicle.params.mass, 1e-6)

        v = max(0.0, v + accel * dt)
        dist += v * dt
        time_s += dt

        log["time"].append(time_s)
        log["distance"].append(dist)
        log["velocity_kph"].append(v * 3.6)
        log["power_in_kw"].append(power_in_kw)
        log["energy_used_kwh"].append(energy_used_kwh)

        if coasting and v < 0.1:
            break

    return {
        "power_limit_kw": float(power_limit_kw),
        "distance_m": float(dist),
        "time_s": float(time_s),
        "energy_used_kwh": float(energy_used_kwh),
        "series": log,
    }


def run_lift_coast(power_limits_kw: list[float], energy_target_kwh: float, dt: float, parameter_overrides: dict | None = None) -> dict:
    from vehicle.vehicle import create_vehicle

    cfg = _load_base_config()
    cfg = copy.deepcopy(cfg)
    vehicle = create_vehicle(cfg)

    from app.security.vehicle_params import canonical_or_reject
    for key, value in (parameter_overrides or {}).items():
        try:
            canonical = canonical_or_reject(key)
        except ValueError:
            from fastapi import HTTPException
            raise HTTPException(status_code=422, detail=f"Parameter {key!r} is not overridable")
        setattr(vehicle.params, canonical, value)

    runs = [_run_single(vehicle, float(p), float(energy_target_kwh), float(dt)) for p in power_limits_kw]

    return {
        "energy_target_kwh": float(energy_target_kwh),
        "dt": float(dt),
        "runs": runs,
    }
