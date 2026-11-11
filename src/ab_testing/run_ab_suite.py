import argparse
import copy
import csv
import json
import math
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from statistics import mean

import numpy as np


SRC_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SRC_ROOT not in sys.path:
    sys.path.insert(0, SRC_ROOT)


MILESTONE4_FALLBACK_THRESHOLDS = {
    "FSUK": 0.15,
    "SkidpadF26": 0.15,
    "StraightLineTrack": 0.05,
}


MILESTONE4_SOLVER_SUCCESS_THRESHOLDS = {
    "FSUK": 0.85,
    "SkidpadF26": 0.85,
    "StraightLineTrack": 0.95,
}


def load_config(config_path):
    with open(config_path, "r") as f:
        return json.load(f)


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)


def level_values(nominal, pct=0.2):
    if not isinstance(nominal, (int, float)):
        raise TypeError(f"Focused sweep expects numeric parameter, got {type(nominal).__name__}")
    low = nominal * (1.0 - pct)
    high = nominal * (1.0 + pct)
    return [("low", low), ("nominal", nominal), ("high", high)]


def canonical_param(param_name):
    return {
        "aero_cp": "aero_centre_of_pressure",
    }.get(param_name, param_name)


def limiter_fractions(modes):
    if not modes:
        return {}
    counts = Counter(modes)
    total = sum(counts.values())
    if total <= 0:
        return {}
    return {k: v / total for k, v in counts.items()}


def finite_percentile(values, pct):
    finite_vals = [float(v) for v in values if isinstance(v, (int, float)) and math.isfinite(float(v))]
    if not finite_vals:
        return ""
    return float(np.percentile(finite_vals, pct))


def finite_max(values):
    finite_vals = [float(v) for v in values if isinstance(v, (int, float)) and math.isfinite(float(v))]
    if not finite_vals:
        return ""
    return float(max(finite_vals))


def run_suite(
    output_dir,
    include_tracks,
    stale_threshold,
    variant_names,
    fallback_threshold,
    max_out_of_domain_count,
    enforce_milestone4_gates,
    enforce_milestone3_gates,
    enforce_milestone5_gates,
    enforce_milestone6_gates,
    scenario_name,
    scenario_grip_scale,
    scenario_air_density_scale,
    milestone5_max_abs_glat_g,
    milestone5_max_gtotal_g,
):
    from track.track import load_track
    from vehicle.vehicle import create_vehicle
    from simulator.simulator import run_lap_time_simulation

    config_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "config.json"))
    base_config = load_config(config_path)

    variant_map = {name: name for name in variant_names}

    track_map = {
        "FSUK": "datasets/tracks/FSUK.txt",
        "SkidpadF26": "datasets/tracks/SkidpadF26.txt",
        "StraightLineTrack": "datasets/tracks/StraightLineTrack.txt",
    }

    sweep_params = [
        "downforce_coefficient",
        "aero_cp",
        "cog_z",
        "front_track_width",
        "rear_track_width",
        "roll_stiffness",
        "max_roll_angle_deg",
        "base_mu",
    ]

    rows = []
    for track_name in include_tracks:
        track_path = track_map[track_name]
        for variant_name, variant_value in variant_map.items():
            # Create a fresh baseline vehicle to pull nominal parameter values.
            config_for_nominal = copy.deepcopy(base_config)
            config_for_nominal["track"]["file_path"] = track_path
            config_for_nominal.setdefault("ab_testing", {})["model_variant"] = variant_value
            nominal_vehicle = create_vehicle(config_for_nominal)

            for param in sweep_params:
                attr_name = canonical_param(param)
                nominal = getattr(nominal_vehicle.params, attr_name)

                for level_name, level_value in level_values(nominal, pct=0.2):
                    run_config = copy.deepcopy(config_for_nominal)
                    run_config.setdefault("ab_testing", {})["model_variant"] = variant_value
                    use_rollover_speed_cap = True
                    rollover_mode = "rollover_on"
                    run_config.setdefault("solver", {})["use_rollover_speed_cap"] = True
                    run_config["scenario"] = {
                        "name": scenario_name,
                        "grip_scale": float(scenario_grip_scale),
                        "air_density_scale": float(scenario_air_density_scale),
                    }
                    vehicle = create_vehicle(run_config)
                    setattr(vehicle.params, attr_name, level_value)

                    row = {
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "track": track_name,
                        "track_path": track_path,
                        "variant": variant_name,
                        "model_variant": variant_value,
                        "scenario_name": scenario_name,
                        "scenario_grip_scale": float(scenario_grip_scale),
                        "scenario_air_density_scale": float(scenario_air_density_scale),
                        "rollover_mode": rollover_mode,
                        "use_rollover_speed_cap": use_rollover_speed_cap,
                        "parameter": param,
                        "parameter_attr": attr_name,
                        "level": level_name,
                        "parameter_value": level_value,
                        "status": "valid",
                        "reason": "",
                        "lap_time_s": "",
                        "fallback_rate": "",
                        "forward_dominant_mode": "",
                        "backward_dominant_mode": "",
                        "forward_mode_breakdown": "",
                        "backward_mode_breakdown": "",
                        "fallback_gate_pass": "",
                        "fallback_gate_track_threshold": "",
                        "fallback_gate_track_pass": "",
                        "corner_solver_success_rate": "",
                        "solver_success_gate_threshold": "",
                        "solver_success_gate_pass": "",
                        "normal_load_non_physical_events_total": "",
                        "normal_load_non_physical_corner": "",
                        "normal_load_non_physical_forward": "",
                        "normal_load_non_physical_backward": "",
                        "normal_load_gate_pass": "",
                        "peak_abs_g_lat": "",
                        "peak_g_total": "",
                        "milestone5_layerc_pass": "",
                        "corner_residual_lat_abs_p90": "",
                        "corner_residual_lat_abs_max": "",
                        "corner_residual_yaw_abs_p90": "",
                        "corner_residual_yaw_abs_max": "",
                        "corner_residual_lat_rel_p90": "",
                        "corner_residual_lat_rel_max": "",
                        "corner_residual_yaw_rel_p90": "",
                        "corner_residual_yaw_rel_max": "",
                        "tyre_out_of_domain_total": "",
                        "tyre_out_of_domain_slip": "",
                        "tyre_out_of_domain_load": "",
                        "tyre_domain_gate_pass": "",
                    }

                    try:
                        track = load_track(track_path, run_config.get("debug_mode", False))
                        sim_result = run_lap_time_simulation(track, vehicle, run_config, display=False)
                        diagnostics = getattr(sim_result, "diagnostics", {})

                        fallback_flags = diagnostics.get("corner_fallback_used", [])
                        solver_success_flags = diagnostics.get("corner_solver_success", [])
                        fallback_rate = mean([1.0 if f else 0.0 for f in fallback_flags]) if fallback_flags else 0.0
                        solver_success_rate = mean([1.0 if bool(s) else 0.0 for s in solver_success_flags]) if solver_success_flags else 0.0

                        fallback_track_threshold = float(MILESTONE4_FALLBACK_THRESHOLDS.get(track_name, fallback_threshold))
                        solver_success_threshold = float(MILESTONE4_SOLVER_SUCCESS_THRESHOLDS.get(track_name, 0.85))

                        forward_modes = diagnostics.get("forward_limiting_mode", [])
                        backward_modes = diagnostics.get("backward_limiting_mode", [])
                        forward_breakdown = limiter_fractions(forward_modes)
                        backward_breakdown = limiter_fractions(backward_modes)
                        lat_abs = diagnostics.get("corner_solver_lat_residual_abs", [])
                        yaw_abs = diagnostics.get("corner_solver_yaw_residual_abs", [])
                        lat_rel = diagnostics.get("corner_solver_lat_residual_rel", [])
                        yaw_rel = diagnostics.get("corner_solver_yaw_residual_rel", [])
                        tyre_domain = diagnostics.get("tyre_domain", {}) if isinstance(diagnostics, dict) else {}
                        tyre_out_slip = int(tyre_domain.get("lateral_out_of_domain_slip", 0)) + int(tyre_domain.get("longitudinal_out_of_domain_slip", 0))
                        tyre_out_load = int(tyre_domain.get("lateral_out_of_domain_load", 0)) + int(tyre_domain.get("longitudinal_out_of_domain_load", 0))
                        tyre_out_total = int(tyre_domain.get("out_of_domain_total", tyre_out_slip + tyre_out_load))
                        normal_load_non_physical_corner = int(diagnostics.get("corner_non_physical_normal_load_events", 0))
                        normal_load_non_physical_forward = int(diagnostics.get("forward_non_physical_normal_load_events", 0))
                        normal_load_non_physical_backward = int(diagnostics.get("backward_non_physical_normal_load_events", 0))
                        normal_load_non_physical_total = int(diagnostics.get("normal_load_non_physical_events_total", normal_load_non_physical_corner + normal_load_non_physical_forward + normal_load_non_physical_backward))

                        g_lat_channel = getattr(sim_result, "g_lat_channel", [])
                        g_long_channel = getattr(sim_result, "g_long_channel", [])
                        peak_abs_g_lat = max([abs(float(v)) for v in g_lat_channel], default=0.0)
                        n_g = min(len(g_lat_channel), len(g_long_channel))
                        if n_g > 0:
                            peak_g_total = max(
                                (float(np.sqrt(float(g_lat_channel[i]) ** 2 + float(g_long_channel[i]) ** 2)) for i in range(n_g)),
                                default=0.0,
                            )
                        else:
                            peak_g_total = 0.0

                        row["lap_time_s"] = float(sim_result.lap_time)
                        row["fallback_rate"] = float(fallback_rate)
                        row["fallback_gate_pass"] = bool(fallback_rate <= fallback_threshold)
                        row["fallback_gate_track_threshold"] = float(fallback_track_threshold)
                        row["fallback_gate_track_pass"] = bool(fallback_rate <= fallback_track_threshold)
                        row["corner_solver_success_rate"] = float(solver_success_rate)
                        row["solver_success_gate_threshold"] = float(solver_success_threshold)
                        row["solver_success_gate_pass"] = bool(solver_success_rate >= solver_success_threshold)
                        row["normal_load_non_physical_events_total"] = normal_load_non_physical_total
                        row["normal_load_non_physical_corner"] = normal_load_non_physical_corner
                        row["normal_load_non_physical_forward"] = normal_load_non_physical_forward
                        row["normal_load_non_physical_backward"] = normal_load_non_physical_backward
                        row["normal_load_gate_pass"] = bool(normal_load_non_physical_total == 0)
                        row["peak_abs_g_lat"] = float(peak_abs_g_lat)
                        row["peak_g_total"] = float(peak_g_total)
                        row["milestone5_layerc_pass"] = bool(
                            (track_name != "FSUK")
                            or (
                                float(peak_abs_g_lat) <= float(milestone5_max_abs_glat_g)
                                and float(peak_g_total) <= float(milestone5_max_gtotal_g)
                            )
                        )
                        row["forward_mode_breakdown"] = json.dumps(forward_breakdown, sort_keys=True)
                        row["backward_mode_breakdown"] = json.dumps(backward_breakdown, sort_keys=True)
                        row["forward_dominant_mode"] = max(forward_breakdown, key=forward_breakdown.get) if forward_breakdown else ""
                        row["backward_dominant_mode"] = max(backward_breakdown, key=backward_breakdown.get) if backward_breakdown else ""
                        row["corner_residual_lat_abs_p90"] = finite_percentile(lat_abs, 90)
                        row["corner_residual_lat_abs_max"] = finite_max(lat_abs)
                        row["corner_residual_yaw_abs_p90"] = finite_percentile(yaw_abs, 90)
                        row["corner_residual_yaw_abs_max"] = finite_max(yaw_abs)
                        row["corner_residual_lat_rel_p90"] = finite_percentile(lat_rel, 90)
                        row["corner_residual_lat_rel_max"] = finite_max(lat_rel)
                        row["corner_residual_yaw_rel_p90"] = finite_percentile(yaw_rel, 90)
                        row["corner_residual_yaw_rel_max"] = finite_max(yaw_rel)
                        row["tyre_out_of_domain_total"] = tyre_out_total
                        row["tyre_out_of_domain_slip"] = tyre_out_slip
                        row["tyre_out_of_domain_load"] = tyre_out_load
                        if max_out_of_domain_count >= 0:
                            row["tyre_domain_gate_pass"] = bool(tyre_out_total <= max_out_of_domain_count)

                    except Exception as exc:
                        row["status"] = "invalid"
                        row["reason"] = f"{type(exc).__name__}: {exc}"

                    rows.append(row)

    ensure_dir(output_dir)
    runs_csv = os.path.join(output_dir, "ab_runs.csv")
    with open(runs_csv, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    # Sensitivity summary per track x variant x parameter
    grouped = defaultdict(list)
    for r in rows:
        if r["status"] != "valid" or r["lap_time_s"] == "":
            continue
        key = (r["track"], r["variant"], r["parameter"])
        grouped[key].append(float(r["lap_time_s"]))

    sens_rows = []
    for (track_name, variant_name, parameter), lap_times in grouped.items():
        if not lap_times:
            continue
        delta = max(lap_times) - min(lap_times)
        sens_rows.append(
            {
                "track": track_name,
                "variant": variant_name,
                "parameter": parameter,
                "delta_lap_time_s": delta,
                "stale": delta < stale_threshold,
                "samples": len(lap_times),
            }
        )

    sens_csv = os.path.join(output_dir, "ab_sensitivity.csv")
    with open(sens_csv, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["track", "variant", "parameter", "delta_lap_time_s", "stale", "samples"])
        writer.writeheader()
        writer.writerows(sens_rows)

    # Markdown summary
    invalid_count = sum(1 for r in rows if r["status"] == "invalid")
    total_count = len(rows)
    stale_counts = Counter((r["track"], r["variant"]) for r in sens_rows if r["stale"])
    valid_rows = [r for r in rows if r["status"] == "valid" and r["fallback_rate"] != ""]
    fallback_fail_counts = Counter(
        (r["track"], r["variant"])
        for r in valid_rows
        if float(r["fallback_rate"]) > float(fallback_threshold)
    )
    fallback_track_fail_counts = Counter(
        (r["track"], r["variant"])
        for r in valid_rows
        if float(r.get("fallback_gate_track_pass", 1.0)) == 0.0
    )
    solver_success_fail_counts = Counter(
        (r["track"], r["variant"])
        for r in valid_rows
        if float(r.get("solver_success_gate_pass", 1.0)) == 0.0
    )
    normal_load_gate_fail_counts = Counter(
        (r["track"], r["variant"])
        for r in valid_rows
        if float(r.get("normal_load_non_physical_events_total", 0.0)) > 0.0
    )
    tyre_domain_fail_counts = Counter(
        (r["track"], r["variant"])
        for r in valid_rows
        if max_out_of_domain_count >= 0 and float(r.get("tyre_out_of_domain_total", 0.0)) > float(max_out_of_domain_count)
    )
    milestone5_layerc_fail_counts = Counter(
        (r["track"], r["variant"])
        for r in valid_rows
        if (r.get("track") == "FSUK") and (float(r.get("milestone5_layerc_pass", 1.0)) == 0.0)
    )
    rollover_modes_present = sorted({r.get("rollover_mode", "") for r in rows if r.get("rollover_mode", "")})

    residual_summary = {}
    tyre_domain_summary = {}
    milestone3_gate_summary = {}
    milestone6_gate_summary = {}
    for track_name in include_tracks:
        for variant_name in variant_names:
            subset = [
                r for r in valid_rows
                if r["track"] == track_name and r["variant"] == variant_name
            ]
            is_straight_like_track = str(track_name).strip().lower() == "straightlinetrack"
            base_mu_gate_enforced = str(track_name).strip().lower() == "fsuk"
            residual_summary[(track_name, variant_name)] = {
                "lat_abs_max": finite_max([r.get("corner_residual_lat_abs_max", "") for r in subset]),
                "yaw_abs_max": finite_max([r.get("corner_residual_yaw_abs_max", "") for r in subset]),
                "lat_rel_p90": finite_percentile([r.get("corner_residual_lat_rel_p90", "") for r in subset], 90),
                "yaw_rel_p90": finite_percentile([r.get("corner_residual_yaw_rel_p90", "") for r in subset], 90),
            }
            tyre_domain_summary[(track_name, variant_name)] = {
                "out_total_max": finite_max([r.get("tyre_out_of_domain_total", "") for r in subset]),
                "out_slip_max": finite_max([r.get("tyre_out_of_domain_slip", "") for r in subset]),
                "out_load_max": finite_max([r.get("tyre_out_of_domain_load", "") for r in subset]),
            }

            level_by_param = defaultdict(dict)
            for r in subset:
                level_by_param[r.get("parameter", "")][r.get("level", "")] = r

            cog_sign_pass = True
            if (not is_straight_like_track) and "cog_z" in level_by_param and ("low" in level_by_param["cog_z"]) and ("high" in level_by_param["cog_z"]):
                low_lap = float(level_by_param["cog_z"]["low"]["lap_time_s"])
                high_lap = float(level_by_param["cog_z"]["high"]["lap_time_s"])
                # Higher CoG should not improve lap-time realism metrics.
                cog_sign_pass = bool(high_lap >= low_lap - 1e-6)

            base_mu_nontrivial_pass = False
            base_mu_delta = ""
            if is_straight_like_track:
                base_mu_nontrivial_pass = True
                base_mu_delta = "n/a"
            elif "base_mu" in level_by_param and ("low" in level_by_param["base_mu"]) and ("high" in level_by_param["base_mu"]):
                low_lap = float(level_by_param["base_mu"]["low"]["lap_time_s"])
                high_lap = float(level_by_param["base_mu"]["high"]["lap_time_s"])
                base_mu_delta = abs(high_lap - low_lap)
                base_mu_nontrivial_pass = bool(base_mu_delta > 1e-3)

            normal_load_pass = all(float(r.get("normal_load_non_physical_events_total", 0.0)) == 0.0 for r in subset)
            milestone3_gate_summary[(track_name, variant_name)] = {
                "normal_load_pass": bool(normal_load_pass),
                "cog_sign_pass": bool(cog_sign_pass),
                "base_mu_nontrivial_pass": bool(base_mu_nontrivial_pass),
                "base_mu_delta": base_mu_delta,
                "base_mu_gate_enforced": bool(base_mu_gate_enforced),
            }
            milestone6_gate_summary[(track_name, variant_name)] = {
                "scenario_context_present": all(
                    str(r.get("scenario_name", "")).strip() != ""
                    and r.get("scenario_grip_scale", "") != ""
                    and r.get("scenario_air_density_scale", "") != ""
                    for r in subset
                ),
                "scenario_scales_positive": all(
                    float(r.get("scenario_grip_scale", 0.0)) > 0.0
                    and float(r.get("scenario_air_density_scale", 0.0)) > 0.0
                    for r in subset
                ),
            }

    md_path = os.path.join(output_dir, "ab_summary.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# A/B Diagnostic Summary\n\n")
        f.write(f"- Generated: {datetime.now(timezone.utc).isoformat()}\n")
        f.write(f"- Total runs: {total_count}\n")
        f.write(f"- Invalid runs: {invalid_count}\n")
        f.write(f"- Tracks: {', '.join(include_tracks)}\n")
        f.write(f"- Variants: {', '.join(variant_names)}\n")
        if rollover_modes_present:
            f.write(f"- Rollover modes in this run: {', '.join(rollover_modes_present)}\n")
        f.write("- Focused parameters: downforce_coefficient, aero_cp, cog_z, front_track_width, rear_track_width, roll_stiffness, max_roll_angle_deg, base_mu\n\n")
        f.write(f"- Fallback-rate gate: pass when fallback_rate <= {fallback_threshold:.3f}\n")
        if enforce_milestone4_gates:
            f.write("- Milestone 4 track gates: enabled (track-specific fallback and solver-success thresholds)\n")
        else:
            f.write("- Milestone 4 track gates: disabled\n")
        if enforce_milestone3_gates:
            f.write("- Milestone 3 gates: enabled (normal-load physics + sensitivity sign checks)\n")
        else:
            f.write("- Milestone 3 gates: disabled\n")
        if enforce_milestone5_gates:
            f.write("- Milestone 5 Layer C gate: enabled (FSUK peak |g_lat| and g_total limits)\n")
            f.write(
                f"- Milestone 5 Layer C thresholds: peak |g_lat| <= {float(milestone5_max_abs_glat_g)}, peak g_total <= {float(milestone5_max_gtotal_g)}\n"
            )
        else:
            f.write("- Milestone 5 Layer C gate: disabled\n")
        if enforce_milestone6_gates:
            f.write("- Milestone 6 scenario-separation gate: enabled (explicit scenario context + positive multipliers)\n")
        else:
            f.write("- Milestone 6 scenario-separation gate: disabled\n")
        f.write(f"- Scenario context: name={scenario_name}, grip_scale={float(scenario_grip_scale)}, air_density_scale={float(scenario_air_density_scale)}\n")
        if max_out_of_domain_count >= 0:
            f.write(f"- Tyre-domain gate: pass when tyre_out_of_domain_total <= {int(max_out_of_domain_count)}\n")
            f.write(f"- Tyre-domain gate failures (runs): {sum(tyre_domain_fail_counts.values())}\n")
        else:
            f.write("- Tyre-domain gate: reporting only (no hard fail threshold)\n")
        f.write("\n")

        f.write("## Invalid Run Breakdown\n\n")
        if invalid_count == 0:
            f.write("All runs completed as valid.\n\n")
        else:
            reasons = Counter(r["reason"] for r in rows if r["status"] == "invalid")
            for reason, count in reasons.most_common():
                f.write(f"- {count}x {reason}\n")
            f.write("\n")

        f.write("## Stale Metric Count by Track/Variant\n\n")
        for track_name in include_tracks:
            for variant_name in variant_names:
                f.write(f"- {track_name} / {variant_name}: {stale_counts.get((track_name, variant_name), 0)} stale parameters\n")
        f.write("\n")

        f.write("## Fallback-Rate Gate Failures by Track/Variant\n\n")
        for track_name in include_tracks:
            for variant_name in variant_names:
                f.write(f"- {track_name} / {variant_name}: {fallback_fail_counts.get((track_name, variant_name), 0)} runs above threshold\n")
        f.write("\n")

        f.write("## Milestone 4 Track Gate Failures by Track/Variant\n\n")
        if not enforce_milestone4_gates:
            f.write("Milestone 4 track gates disabled.\n")
        else:
            for track_name in include_tracks:
                for variant_name in variant_names:
                    f.write(
                        f"- {track_name} / {variant_name}: "
                        f"fallback_track_gate_fails={fallback_track_fail_counts.get((track_name, variant_name), 0)}, "
                        f"solver_success_gate_fails={solver_success_fail_counts.get((track_name, variant_name), 0)}\n"
                    )
        f.write("\n")

        f.write("## Milestone 3 Gate Status by Track/Variant\n\n")
        for track_name in include_tracks:
            for variant_name in variant_names:
                stats = milestone3_gate_summary[(track_name, variant_name)]
                f.write(
                    f"- {track_name} / {variant_name}: "
                    f"normal_load_pass={stats['normal_load_pass']}, "
                    f"cog_sign_pass={stats['cog_sign_pass']}, "
                    f"base_mu_nontrivial_pass={stats['base_mu_nontrivial_pass']}, "
                    f"base_mu_delta={stats['base_mu_delta']}, "
                    f"base_mu_gate_enforced={stats['base_mu_gate_enforced']}\n"
                )
        f.write("\n")

        f.write("## Milestone 5 Layer C Gate Failures by Track/Variant\n\n")
        if not enforce_milestone5_gates:
            f.write("Milestone 5 Layer C gate disabled.\n")
        else:
            for track_name in include_tracks:
                for variant_name in variant_names:
                    f.write(f"- {track_name} / {variant_name}: layerc_gate_fails={milestone5_layerc_fail_counts.get((track_name, variant_name), 0)}\n")
        f.write("\n")

        f.write("## Milestone 6 Scenario Separation Status by Track/Variant\n\n")
        for track_name in include_tracks:
            for variant_name in variant_names:
                stats = milestone6_gate_summary[(track_name, variant_name)]
                f.write(
                    f"- {track_name} / {variant_name}: "
                    f"scenario_context_present={stats['scenario_context_present']}, "
                    f"scenario_scales_positive={stats['scenario_scales_positive']}\n"
                )
        f.write("\n")

        f.write("## Tyre-Domain Gate Failures by Track/Variant\n\n")
        if max_out_of_domain_count < 0:
            f.write("Tyre-domain gate disabled (reporting mode only).\n")
        else:
            for track_name in include_tracks:
                for variant_name in variant_names:
                    f.write(f"- {track_name} / {variant_name}: {tyre_domain_fail_counts.get((track_name, variant_name), 0)} runs above threshold\n")
        f.write("\n")

        f.write("## Corner Residual Telemetry (Track/Variant)\n\n")
        f.write("- Metrics summarize residual channels emitted by corner equilibrium solving.\n")
        for track_name in include_tracks:
            for variant_name in variant_names:
                stats = residual_summary[(track_name, variant_name)]
                f.write(
                    f"- {track_name} / {variant_name}: "
                    f"lat_abs_max={stats['lat_abs_max']}, "
                    f"yaw_abs_max={stats['yaw_abs_max']}, "
                    f"lat_rel_p90={stats['lat_rel_p90']}, "
                    f"yaw_rel_p90={stats['yaw_rel_p90']}\n"
                )
        f.write("\n")

        f.write("## Tyre Validity-Domain Usage (Track/Variant)\n\n")
        f.write("- Counts summarize out-of-domain slip/load usage observed during simulation calls.\n")
        for track_name in include_tracks:
            for variant_name in variant_names:
                stats = tyre_domain_summary[(track_name, variant_name)]
                f.write(
                    f"- {track_name} / {variant_name}: "
                    f"out_total_max={stats['out_total_max']}, "
                    f"out_slip_max={stats['out_slip_max']}, "
                    f"out_load_max={stats['out_load_max']}\n"
                )
        f.write("\n")

        f.write("## Top Sensitivity Movers\n\n")
        ranked = sorted(sens_rows, key=lambda r: r["delta_lap_time_s"], reverse=True)
        for row in ranked[:12]:
            f.write(
                f"- {row['track']} / {row['variant']} / {row['parameter']}: "
                f"delta_lap_time_s={row['delta_lap_time_s']:.4f}, stale={row['stale']}\n"
            )

    tyre_domain_fail_total = sum(tyre_domain_fail_counts.values()) if max_out_of_domain_count >= 0 else 0
    milestone4_fail_total = 0
    milestone3_fail_total = 0
    milestone5_fail_total = 0
    milestone6_fail_total = 0
    if enforce_milestone4_gates:
        milestone4_fail_total = int(sum(fallback_track_fail_counts.values()) + sum(solver_success_fail_counts.values()))
    if enforce_milestone3_gates:
        for track_name in include_tracks:
            for variant_name in variant_names:
                stats = milestone3_gate_summary[(track_name, variant_name)]
                base_mu_gate_ok = True
                if stats.get("base_mu_gate_enforced", False):
                    base_mu_gate_ok = bool(stats["base_mu_nontrivial_pass"])
                if not (stats["normal_load_pass"] and stats["cog_sign_pass"] and base_mu_gate_ok):
                    milestone3_fail_total += 1
    if enforce_milestone5_gates:
        milestone5_fail_total = int(sum(milestone5_layerc_fail_counts.values()))
    if enforce_milestone6_gates:
        for track_name in include_tracks:
            for variant_name in variant_names:
                stats = milestone6_gate_summary[(track_name, variant_name)]
                if not (stats["scenario_context_present"] and stats["scenario_scales_positive"]):
                    milestone6_fail_total += 1

    return (
        runs_csv,
        sens_csv,
        md_path,
        tyre_domain_fail_total,
        milestone4_fail_total,
        milestone3_fail_total,
        milestone5_fail_total,
        milestone6_fail_total,
    )


def main():
    parser = argparse.ArgumentParser(description="Run A/B diagnostic suite (Baseline vs B1) and generate CSV + Markdown outputs.")
    parser.add_argument("--output-dir", default="ab_test_outputs", help="Directory for generated artifacts")
    parser.add_argument(
        "--tracks",
        default="FSUK,SkidpadF26,StraightLineTrack",
        help="Comma-separated track set: FSUK,SkidpadF26,StraightLineTrack",
    )
    parser.add_argument(
        "--variants",
        default="baseline,b1,tyre_peak_load_clamp",
        help="Comma-separated model variants to compare",
    )
    parser.add_argument("--stale-threshold", type=float, default=0.05, help="Delta lap-time threshold (s) for stale flag")
    parser.add_argument("--fallback-threshold", type=float, default=0.15, help="Fallback-rate pass threshold")
    parser.add_argument(
        "--max-out-of-domain-count",
        type=int,
        default=-1,
        help="Tyre-domain hard gate threshold; set -1 for reporting-only mode",
    )
    parser.add_argument(
        "--enforce-milestone4-gates",
        action="store_true",
        help="Enable Milestone 4 track-specific hard gates for fallback rate and solver success",
    )
    parser.add_argument(
        "--enforce-milestone3-gates",
        action="store_true",
        help="Enable Milestone 3 hard gates for normal-load events and sensitivity sign checks",
    )
    parser.add_argument(
        "--enforce-milestone5-gates",
        action="store_true",
        help="Enable Milestone 5 Layer C hard gate for FSUK realism limits",
    )
    parser.add_argument(
        "--enforce-milestone6-gates",
        action="store_true",
        help="Enable Milestone 6 scenario-separation gate checks",
    )
    parser.add_argument("--scenario-name", default="baseline", help="Scenario context label")
    parser.add_argument("--scenario-grip-scale", type=float, default=1.0, help="Scenario multiplier for tyre grip")
    parser.add_argument("--scenario-air-density-scale", type=float, default=1.0, help="Scenario multiplier for ambient air density")
    parser.add_argument("--m5-max-abs-glat-g", type=float, default=2.0, help="Milestone 5 FSUK peak |g_lat| gate")
    parser.add_argument("--m5-max-gtotal-g", type=float, default=3.0, help="Milestone 5 FSUK peak g_total gate")
    args = parser.parse_args()

    include_tracks = [t.strip() for t in args.tracks.split(",") if t.strip()]
    variant_names = [v.strip() for v in args.variants.split(",") if v.strip()]
    if not variant_names:
        raise ValueError("At least one variant is required")

    (
        runs_csv,
        sens_csv,
        md_path,
        tyre_domain_fail_total,
        milestone4_fail_total,
        milestone3_fail_total,
        milestone5_fail_total,
        milestone6_fail_total,
    ) = run_suite(
        output_dir=args.output_dir,
        include_tracks=include_tracks,
        stale_threshold=args.stale_threshold,
        variant_names=variant_names,
        fallback_threshold=args.fallback_threshold,
        max_out_of_domain_count=args.max_out_of_domain_count,
        enforce_milestone4_gates=bool(args.enforce_milestone4_gates),
        enforce_milestone3_gates=bool(args.enforce_milestone3_gates),
        enforce_milestone5_gates=bool(args.enforce_milestone5_gates),
        enforce_milestone6_gates=bool(args.enforce_milestone6_gates),
        scenario_name=str(args.scenario_name),
        scenario_grip_scale=float(args.scenario_grip_scale),
        scenario_air_density_scale=float(args.scenario_air_density_scale),
        milestone5_max_abs_glat_g=float(args.m5_max_abs_glat_g),
        milestone5_max_gtotal_g=float(args.m5_max_gtotal_g),
    )

    if args.max_out_of_domain_count >= 0 and tyre_domain_fail_total > 0:
        print("A/B suite failed tyre-domain gate")
        print(f"Runs above threshold: {tyre_domain_fail_total}")
        print(f"Threshold: {args.max_out_of_domain_count}")
        print(f"Runs CSV: {runs_csv}")
        print(f"Summary Markdown: {md_path}")
        raise SystemExit(1)

    if args.enforce_milestone4_gates and milestone4_fail_total > 0:
        print("A/B suite failed Milestone 4 track gates")
        print(f"Gate violations: {milestone4_fail_total}")
        print("Track fallback thresholds: FSUK<=0.15, SkidpadF26<=0.15, StraightLineTrack<=0.05")
        print("Track solver-success thresholds: FSUK>=0.85, SkidpadF26>=0.85, StraightLineTrack>=0.95")
        print(f"Runs CSV: {runs_csv}")
        print(f"Summary Markdown: {md_path}")
        raise SystemExit(1)

    if args.enforce_milestone3_gates and milestone3_fail_total > 0:
        print("A/B suite failed Milestone 3 gates")
        print(f"Track/variant gate failures: {milestone3_fail_total}")
        print("Milestone 3 gates: normal-load non-physical events must be zero, cog_z sign check must pass, base_mu sensitivity must be non-trivial")
        print(f"Runs CSV: {runs_csv}")
        print(f"Summary Markdown: {md_path}")
        raise SystemExit(1)

    if args.enforce_milestone5_gates and milestone5_fail_total > 0:
        print("A/B suite failed Milestone 5 Layer C gate")
        print(f"Layer C gate failures: {milestone5_fail_total}")
        print(f"FSUK limits: peak |g_lat| <= {float(args.m5_max_abs_glat_g)}, peak g_total <= {float(args.m5_max_gtotal_g)}")
        print(f"Runs CSV: {runs_csv}")
        print(f"Summary Markdown: {md_path}")
        raise SystemExit(1)

    if args.enforce_milestone6_gates and milestone6_fail_total > 0:
        print("A/B suite failed Milestone 6 scenario-separation gate")
        print(f"Scenario gate failures: {milestone6_fail_total}")
        print("Scenario context must be explicit and scenario multipliers must remain positive.")
        print(f"Runs CSV: {runs_csv}")
        print(f"Summary Markdown: {md_path}")
        raise SystemExit(1)

    print("A/B suite complete")
    print(f"Runs CSV: {runs_csv}")
    print(f"Sensitivity CSV: {sens_csv}")
    print(f"Summary Markdown: {md_path}")


if __name__ == "__main__":
    main()
