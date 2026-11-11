"""Evaluate braking realism and explain longitudinal braking capacity.

This is a numeric eval, not an LLM eval. It runs the simulator with the default
config and a load-transfer variant, then checks that braking is not being made
plausible by a hard deceleration clip.
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from simulator.simulator import run_lap_time_simulation
from simulator.util.calcSpeedProfile import _compute_total_force_caps
from track.track import load_track
from vehicle.vehicle import create_vehicle


def _load_config() -> dict[str, Any]:
    return json.loads((REPO_ROOT / "config.json").read_text(encoding="utf-8"))


def _run_case(name: str, cfg: dict[str, Any]) -> dict[str, Any]:
    track = load_track(cfg["track"]["file_path"], cfg.get("debug_mode", False))
    vehicle = create_vehicle(cfg)
    result = run_lap_time_simulation(track, vehicle, cfg, display=False)
    diagnostics = result.diagnostics

    g_lat = np.asarray(result.g_lat_channel, dtype=float)
    g_long = np.asarray(result.g_long_channel, dtype=float)
    g_total = np.sqrt(g_lat**2 + g_long**2)
    raw_brake_g = np.asarray(diagnostics.get("backward_brake_decel_limit_raw", []), dtype=float) / 9.81
    used_brake_g = np.asarray(diagnostics.get("backward_brake_decel_limit", []), dtype=float) / 9.81

    static_load = vehicle.compute_static_normal_load()
    fx_cap_static, fy_cap_static = _compute_total_force_caps(
        vehicle=vehicle,
        front_load=static_load,
        rear_load=static_load,
        config=cfg,
        peak_slip_ratio=-float(cfg.get("ab_testing", {}).get("peak_slip_ratio_brake", 12.0)),
    )
    tyre_diag = vehicle.tyre_model.get_domain_diagnostics()
    long_mu_ref = float(tyre_diag.get("longitudinal_peak_mu_reference", 1.0))

    return {
        "case": name,
        "model_variant": cfg.get("ab_testing", {}).get("model_variant", cfg.get("model_variant", "baseline")),
        "hard_brake_decel_cap_configured": cfg.get("solver", {}).get("max_brake_decel_g") is not None,
        "lap_time_s": float(result.lap_time),
        "max_abs_g_lat": float(np.max(np.abs(g_lat))) if g_lat.size else 0.0,
        "g_long_min": float(np.min(g_long)) if g_long.size else 0.0,
        "g_long_max": float(np.max(g_long)) if g_long.size else 0.0,
        "g_total_max": float(np.max(g_total)) if g_total.size else 0.0,
        "g_total_p90": float(np.percentile(g_total, 90)) if g_total.size else 0.0,
        "raw_brake_decel_g_max": float(np.nanmax(raw_brake_g)) if raw_brake_g.size else 0.0,
        "raw_brake_decel_g_p95": float(np.nanpercentile(raw_brake_g, 95)) if raw_brake_g.size else 0.0,
        "used_brake_decel_g_max": float(np.nanmax(used_brake_g)) if used_brake_g.size else 0.0,
        "used_brake_decel_g_p95": float(np.nanpercentile(used_brake_g, 95)) if used_brake_g.size else 0.0,
        "backward_brake_decel_cap_applied_events": int(diagnostics.get("backward_brake_decel_cap_applied_events", 0)),
        "backward_limiting_mode_counts": dict(Counter(diagnostics.get("backward_limiting_mode", []))),
        "corner_fallback_count": int(sum(1 for x in diagnostics.get("corner_fallback_used", []) if x)),
        "normal_load_non_physical_events_total": int(diagnostics.get("normal_load_non_physical_events_total", 0)),
        "normal_load_transfer_clamped_events_total": int(diagnostics.get("normal_load_transfer_clamped_events_total", 0)),
        "static_longitudinal_tyre_cap_g": float(fx_cap_static / (vehicle.params.mass * 9.81)),
        "static_lateral_tyre_cap_g": float(fy_cap_static / (vehicle.params.mass * 9.81)),
        "tyre_longitudinal_peak_mu_reference": long_mu_ref,
        "tyre_longitudinal_base_mu_scale": float(tyre_diag.get("longitudinal_base_mu_scale", 0.0)),
        "legacy_double_scale_static_longitudinal_cap_g_estimate": float(
            (fx_cap_static / (vehicle.params.mass * 9.81)) * long_mu_ref
        ),
    }


def _gate(cases: list[dict[str, Any]], max_brake_g: float, max_total_g: float) -> dict[str, Any]:
    failures: list[str] = []
    for case in cases:
        name = case["case"]
        if case["hard_brake_decel_cap_configured"]:
            failures.append(f"{name}: hard brake decel cap is configured")
        if case["backward_brake_decel_cap_applied_events"] != 0:
            failures.append(f"{name}: brake decel cap applied")
        if abs(case["g_long_min"]) > max_brake_g:
            failures.append(f"{name}: max braking {abs(case['g_long_min']):.3f}g exceeds {max_brake_g:.3f}g")
        if case["g_total_max"] > max_total_g:
            failures.append(f"{name}: total g {case['g_total_max']:.3f}g exceeds {max_total_g:.3f}g")
        if case["static_longitudinal_tyre_cap_g"] > max_brake_g:
            failures.append(
                f"{name}: static longitudinal tyre cap {case['static_longitudinal_tyre_cap_g']:.3f}g exceeds {max_brake_g:.3f}g"
            )
    return {"passed": not failures, "failures": failures}


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate braking model realism and decomposition.")
    parser.add_argument("--max-brake-g", type=float, default=2.4)
    parser.add_argument("--max-total-g", type=float, default=2.6)
    parser.add_argument("--output", default=str(REPO_ROOT / "artifacts" / "evals" / "braking_model_eval.json"))
    args = parser.parse_args()

    base = _load_config()
    base.setdefault("solver", {}).pop("max_brake_decel_g", None)

    b1 = copy.deepcopy(base)
    b1.setdefault("ab_testing", {})["model_variant"] = "b1"

    cases = [
        _run_case("default_no_hard_brake_cap", base),
        _run_case("b1_load_transfer_no_hard_brake_cap", b1),
    ]
    gate = _gate(cases, max_brake_g=args.max_brake_g, max_total_g=args.max_total_g)

    payload = {
        "gate": gate,
        "thresholds": {
            "max_brake_g": args.max_brake_g,
            "max_total_g": args.max_total_g,
        },
        "cases": cases,
        "interpretation": [
            "A passing result means braking is not being made plausible by solver.max_brake_decel_g.",
            "legacy_double_scale_static_longitudinal_cap_g_estimate estimates the old behavior where base_mu multiplied an already-frictional tyre peak.",
            "If legacy estimate is much larger than static_longitudinal_tyre_cap_g, the old overestimate came from double-scaling tyre data.",
        ],
    }

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0 if gate["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
