import json
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from concurrent.futures.process import BrokenProcessPool
from typing import Any
from pathlib import Path

from fastapi import HTTPException

from app.paths import config_path
from app.security.config_overrides import ConfigOverrides, build_config
from app.security.vehicle_params import canonical_or_reject


def _load_base_config() -> dict:
    with open(config_path(), "r", encoding="utf-8") as f:
        return json.load(f)


def _coerce_values(raw_values: str, current_value: Any, steps: int) -> list[Any]:
    """Parse values string to match parameter type. Mirrors src/sweep.py logic."""
    import numpy as np

    raw_values = raw_values.strip()

    if isinstance(current_value, (int, float)) and not isinstance(current_value, bool):
        parts = [p.strip() for p in raw_values.split(",") if p.strip()]
        numeric_values = [float(v) for v in parts]
        if len(numeric_values) == 2 and steps > 1:
            return [float(v) for v in np.linspace(numeric_values[0], numeric_values[1], steps)]
        return numeric_values

    if isinstance(current_value, bool):
        parsed: list[bool] = []
        for token in [p.strip().lower() for p in raw_values.split(",") if p.strip()]:
            if token in {"true", "1", "yes", "y"}:
                parsed.append(True)
            elif token in {"false", "0", "no", "n"}:
                parsed.append(False)
            else:
                raise ValueError(f"Invalid boolean token '{token}'")
        return parsed

    if isinstance(current_value, str):
        values = [p.strip() for p in raw_values.split(",") if p.strip()]
        if not values:
            raise ValueError("No string values supplied")
        return values

    if isinstance(current_value, list):
        candidates: list[list[Any]] = []
        list_groups = [g.strip() for g in raw_values.split(";") if g.strip()]
        for group in list_groups:
            if group.startswith("["):
                parsed_group = json.loads(group)
                if not isinstance(parsed_group, list):
                    raise ValueError("List candidate must be a JSON list")
                candidates.append(parsed_group)
            else:
                tokens = [t.strip() for t in group.split(",") if t.strip()]
                parsed_items: list[Any] = []
                for token in tokens:
                    try:
                        parsed_items.append(float(token))
                    except ValueError:
                        parsed_items.append(token)
                candidates.append(parsed_items)
        if not candidates:
            raise ValueError("No list values supplied")
        return candidates

    raise TypeError(f"Unsupported parameter type: {type(current_value).__name__}")


def _value_label(val: Any) -> str:
    if isinstance(val, float):
        return f"{val:.4g}"
    if isinstance(val, list):
        return str(val)
    return str(val)


def _sweep_max_workers(cfg: dict, candidate_count: int) -> int:
    solver_cfg = cfg.get("solver", {}) if isinstance(cfg, dict) else {}
    raw_workers = solver_cfg.get("sweep_max_workers", None)
    cpu_count = os.cpu_count() or 1
    default_workers = min(4, cpu_count, max(1, candidate_count))
    if raw_workers is None:
        return default_workers
    try:
        return max(1, min(int(raw_workers), candidate_count))
    except (TypeError, ValueError):
        return default_workers


def _run_sweep_candidate(index: int, cfg: dict, canonical_param: str, val: Any) -> tuple[int, dict]:
    from simulator.simulator import run_lap_time_simulation
    from track.track import load_track
    from vehicle.vehicle import create_vehicle

    vehicle = create_vehicle(cfg)
    setattr(vehicle.params, canonical_param, val)
    track = load_track(cfg["track"]["file_path"], cfg.get("debug_mode", False))
    sim_result = run_lap_time_simulation(track, vehicle, cfg, display=False)
    serialisable_val = val if isinstance(val, (int, float, bool)) else str(val)
    return index, {
        "value": serialisable_val,
        "label": _value_label(val),
        "lap_time_s": float(sim_result.lap_time),
    }


def _run_sweep_candidates_sequential(cfg: dict, canonical_param: str, param_values: list[Any]) -> list[dict]:
    results: list[dict] = []
    for idx, val in enumerate(param_values):
        _, result = _run_sweep_candidate(idx, cfg, canonical_param, val)
        results.append(result)
    return results


def run_sweep(
    param: str,
    values: str,
    steps: int = 5,
    parameters: dict | None = None,
    overrides: ConfigOverrides | None = None,
) -> dict:
    from vehicle.vehicle import create_vehicle

    overrides = overrides if overrides is not None else ConfigOverrides()
    try:
        cfg = build_config(_load_base_config(), overrides)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    if parameters is not None:
        cfg["vehicle_parameters"] = parameters

    try:
        canonical_param = canonical_or_reject(param)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    try:
        probe_vehicle = create_vehicle(cfg)
    except KeyError as e:
        raise HTTPException(status_code=422, detail=f"Missing parameter: {e}")

    current_value = getattr(probe_vehicle.params, canonical_param)
    try:
        param_values = _coerce_values(values, current_value, steps)
    except (ValueError, TypeError) as e:
        raise HTTPException(status_code=422, detail=str(e))

    max_workers = _sweep_max_workers(cfg, len(param_values))
    final_results: list[dict]
    if max_workers == 1 or len(param_values) == 1:
        final_results = _run_sweep_candidates_sequential(cfg, canonical_param, param_values)
    else:
        results: list[dict | None] = [None] * len(param_values)
        try:
            with ProcessPoolExecutor(max_workers=max_workers) as pool:
                futures = [
                    pool.submit(_run_sweep_candidate, idx, cfg, canonical_param, val)
                    for idx, val in enumerate(param_values)
                ]
                for future in as_completed(futures):
                    result_idx, result = future.result()
                    results[result_idx] = result
            final_results = [result for result in results if result is not None]
        except BrokenProcessPool:
            final_results = _run_sweep_candidates_sequential(cfg, canonical_param, param_values)

    lap_times = [r["lap_time_s"] for r in final_results]
    best_idx = int(lap_times.index(min(lap_times)))
    worst_idx = int(lap_times.index(max(lap_times)))

    return {
        "param": param,
        "canonical_param": canonical_param,
        "track_file_path": Path(cfg["track"]["file_path"]).name,
        "points": len(final_results),
        "results": final_results,
        "best": final_results[best_idx],
        "worst": final_results[worst_idx],
    }
