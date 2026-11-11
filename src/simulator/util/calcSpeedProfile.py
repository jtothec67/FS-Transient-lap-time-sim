import numpy as np
import logging
from .vehicleDynamics import find_vehicle_state_at_point

logger = logging.getLogger(__name__)


def _get_model_variant(config):
    """Resolve model variant from config with baseline-safe defaults."""
    ab_cfg = config.get('ab_testing', {}) if isinstance(config, dict) else {}
    variant = ab_cfg.get('model_variant', config.get('model_variant', 'baseline')) if isinstance(config, dict) else 'baseline'
    return str(variant).strip().lower()


def _get_scenario_context(config):
    scenario_cfg = config.get('scenario', {}) if isinstance(config, dict) else {}
    name = str(scenario_cfg.get('name', 'baseline')).strip() or 'baseline'
    try:
        grip_scale = float(scenario_cfg.get('grip_scale', 1.0))
    except (TypeError, ValueError):
        grip_scale = 1.0
    try:
        air_density_scale = float(scenario_cfg.get('air_density_scale', 1.0))
    except (TypeError, ValueError):
        air_density_scale = 1.0
    return {
        'name': name,
        'grip_scale': grip_scale,
        'air_density_scale': air_density_scale,
    }


def _is_b1_variant(config):
    variant = _get_model_variant(config)
    return variant in {'b1', 'load_transfer', 'dynamic_normal_load'}


def _get_straight_speed_cap(config):
    """Resolve straight-line speed cap (m/s) for near-zero curvature segments."""
    solver_cfg = config.get('solver', {}) if isinstance(config, dict) else {}
    cap = solver_cfg.get('straight_line_speed_cap_mps', 200.0)
    try:
        return float(cap)
    except (TypeError, ValueError):
        return 200.0


def _get_corner_max_bisection_iters(config):
    """Resolve corner-equilibrium speed-search iterations."""
    solver_cfg = config.get('solver', {}) if isinstance(config, dict) else {}
    iters = solver_cfg.get('corner_max_bisection_iters', 14)
    try:
        return max(1, int(iters))
    except (TypeError, ValueError):
        return 14


def _compute_rollover_speed_cap(curvature, vehicle):
    if abs(curvature) < 1e-9:
        return np.inf
    g = 9.81
    track = max(float(getattr(vehicle.params, 'front_track_width', 1.2)), 1e-6)
    cog_z = max(float(getattr(vehicle.params, 'cog_z', 0.28)), 1e-6)
    radius = 1.0 / abs(curvature)
    return float(np.sqrt((track / (2.0 * cog_z)) * g * radius))


def _compute_tyre_lateral_speed_cap(curvature, vehicle, normal_load_per_tyre, config):
    """Estimate lateral speed cap from tyre lateral force envelope."""
    if abs(curvature) < 1e-9:
        return np.inf
    try:
        slip_angle_cap = float(config.get('solver', {}).get('tyre_lateral_cap_slip_angle_deg', 10.0))
    except (TypeError, ValueError, AttributeError):
        slip_angle_cap = 10.0

    try:
        # No extra mu_scale: base_mu is already embedded in tyre model output (D = peak * base_mu).
        fy_per_tyre = abs(vehicle.tyre_model.get_lateral_force(slip_angle_cap, normal_load=normal_load_per_tyre))
        a_lat_cap = (fy_per_tyre * 4.0) / max(float(vehicle.params.mass), 1e-6)
        if a_lat_cap <= 0.0 or (not np.isfinite(a_lat_cap)):
            return np.inf
        return float(np.sqrt(a_lat_cap / abs(curvature)))
    except Exception:
        return np.inf


def _compute_constrained_fallback_speed(curvature, base_mu, physical_cap_speed, previous_speed, config):
    g = 9.81
    if abs(curvature) > 1e-6:
        v_mu = float(np.sqrt(max(base_mu, 0.0) * g / abs(curvature)))
    else:
        v_mu = float(physical_cap_speed)

    solver_cfg = config.get('solver', {}) if isinstance(config, dict) else {}
    continuity_factor = float(solver_cfg.get('fallback_continuity_cap_factor', 1.08))
    min_continuity_cap = float(solver_cfg.get('fallback_min_speed_cap_mps', 3.0))

    if previous_speed is None or (not np.isfinite(previous_speed)):
        continuity_cap = np.inf
    else:
        continuity_cap = max(min_continuity_cap, float(previous_speed) * continuity_factor)

    return float(min(v_mu, float(physical_cap_speed), continuity_cap))


def _build_retry_tiers(previous_solution, straight_speed_cap, rollover_cap):
    """Build solve-attempt tiers from aggressive to conservative."""
    base_cap = float(straight_speed_cap)
    if np.isfinite(rollover_cap):
        base_cap = min(base_cap, float(rollover_cap))

    prev_speed = None
    if isinstance(previous_solution, dict):
        try:
            prev_speed = float(previous_solution.get('v_car', np.nan))
        except (TypeError, ValueError):
            prev_speed = None
    if prev_speed is not None and not np.isfinite(prev_speed):
        prev_speed = None

    tiers = [
        {
            'name': 'base',
            'initial_guess': None,
            'v_upper_bound_mps': base_cap,
        }
    ]

    if previous_solution is not None:
        warm_cap = base_cap
        if prev_speed is not None:
            warm_cap = min(base_cap, max(5.0, prev_speed * 1.20))
        tiers.append(
            {
                'name': 'warm_start',
                'initial_guess': {
                    'a_steer': float(previous_solution.get('a_steer', 0.0)),
                    'a_sideslip': float(previous_solution.get('a_sideslip', 0.0)),
                },
                'v_upper_bound_mps': warm_cap,
            }
        )

    conservative_cap = base_cap * 0.90
    if prev_speed is not None:
        conservative_cap = min(conservative_cap, max(5.0, prev_speed * 0.95))
    tiers.append(
        {
            'name': 'conservative_bound',
            'initial_guess': previous_solution if isinstance(previous_solution, dict) else None,
            'v_upper_bound_mps': max(5.0, conservative_cap),
        }
    )
    return tiers


def _split_aero_load_by_cp(vehicle, aero_total):
    """Split total aero load between front and rear axles using aero CoP."""
    L = max(float(getattr(vehicle.params, 'wheelbase', 1.6)), 1e-6)
    cp = float(getattr(vehicle.params, 'aero_centre_of_pressure', L * 0.5))
    cp_clamped = min(max(cp, 0.0), L)

    # Static equilibrium about axles: front share decreases as CoP moves rearward.
    rear_frac = cp_clamped / L
    front_frac = 1.0 - rear_frac
    aero_front = float(aero_total) * front_frac
    aero_rear = float(aero_total) * rear_frac
    return aero_front, aero_rear


def _compute_normal_loads_for_longitudinal(vehicle, v_car, a_long, config):
    """
    Compute per-tyre normal loads for front and rear axles.

    Baseline: static normal load per tyre.
    B1: include speed-dependent downforce and quasi-static longitudinal transfer.
    """
    base = vehicle.compute_static_normal_load()
    if not _is_b1_variant(config):
        return {
            'front_per_tyre': base,
            'rear_per_tyre': base,
            'mean_per_tyre': base,
            'total_normal_load': base * 4.0,
            'non_physical_event': False,
            'front_per_tyre_raw': base,
            'rear_per_tyre_raw': base,
        }

    m = vehicle.params.mass
    g = 9.81
    h = vehicle.params.cog_z
    L = max(vehicle.params.wheelbase, 1e-6)
    front_frac = float(vehicle.params.cog_longitudinal_pos)
    front_frac = min(max(front_frac, 0.0), 1.0)
    rear_frac = 1.0 - front_frac

    f_down = max(0.0, vehicle.compute_downforce(v_car))
    total = m * g + f_down

    static_front = (m * g) * front_frac
    static_rear = (m * g) * rear_frac
    aero_front, aero_rear = _split_aero_load_by_cp(vehicle, f_down)

    front_axle = static_front + aero_front
    rear_axle = static_rear + aero_rear

    # Positive longitudinal acceleration shifts load rearward.
    delta_long = (m * a_long * h) / L
    # Bound transferable load so axle normals remain physically feasible.
    min_axle_load = 0.05 * total
    delta_min = -(rear_axle - min_axle_load)
    delta_max = front_axle - min_axle_load
    delta_long_bounded = float(np.clip(delta_long, delta_min, delta_max))
    transfer_clamped = not np.isclose(delta_long_bounded, float(delta_long), rtol=0.0, atol=1e-12)

    front_axle -= delta_long_bounded
    rear_axle += delta_long_bounded

    front_axle_raw = float(front_axle)
    rear_axle_raw = float(rear_axle)
    non_physical_event = (
        (not np.isfinite(front_axle_raw))
        or (not np.isfinite(rear_axle_raw))
        or (front_axle_raw < 0.0)
        or (rear_axle_raw < 0.0)
    )

    # Clamp to keep solver numerically safe in extreme states.
    front_axle = max(0.0, front_axle)
    rear_axle = max(0.0, rear_axle)

    return {
        'front_per_tyre': front_axle / 2.0,
        'rear_per_tyre': rear_axle / 2.0,
        'mean_per_tyre': (front_axle + rear_axle) / 4.0,
        'total_normal_load': front_axle + rear_axle,
        'non_physical_event': bool(non_physical_event),
        'front_per_tyre_raw': front_axle_raw / 2.0,
        'rear_per_tyre_raw': rear_axle_raw / 2.0,
        'transfer_clamped': bool(transfer_clamped),
    }


def _compute_total_force_caps(vehicle, front_load, rear_load, config, peak_slip_ratio):
    """Compute pure-slip total longitudinal and lateral tyre force caps.

    The tyre model (LookupTableTyreModel) already applies base_mu internally when
    computing peak force D = peak_interp(load) * base_mu. Applying mu_scale again
    here would double-count the base friction coefficient. scenario_grip_scale is
    applied separately via vehicle.compute_tyre_forces and is NOT relevant for these
    raw force caps (they are used to compute a budget scale, not absolute forces).
    """
    solver_cfg = config.get('solver', {}) if isinstance(config, dict) else {}
    lateral_cap_slip_angle = float(solver_cfg.get('lateral_combined_slip_angle_deg', 10.0))

    # Longitudinal pure cap from front/rear tyres at requested peak slip ratio.
    # No additional mu_scale: base_mu is already embedded in the tyre model output.
    f_long_front = abs(vehicle.tyre_model.get_longitudinal_force(
        slip_ratio=peak_slip_ratio,
        normal_load=front_load,
    )) * 2.0
    f_long_rear = abs(vehicle.tyre_model.get_longitudinal_force(
        slip_ratio=peak_slip_ratio,
        normal_load=rear_load,
    )) * 2.0
    fx_cap_total = f_long_front + f_long_rear

    # Lateral pure cap proxy using fixed representative slip angle.
    # No additional mu_scale: base_mu is already embedded in the tyre model output.
    f_lat_front = abs(vehicle.tyre_model.get_lateral_force(
        slip_angle=lateral_cap_slip_angle,
        normal_load=front_load,
    )) * 2.0
    f_lat_rear = abs(vehicle.tyre_model.get_lateral_force(
        slip_angle=lateral_cap_slip_angle,
        normal_load=rear_load,
    )) * 2.0
    fy_cap_total = f_lat_front + f_lat_rear

    return float(fx_cap_total), float(fy_cap_total)


def _longitudinal_budget_scale_from_lateral_demand(fy_demand_total, fy_cap_total):
    """Friction-ellipse budget scale for longitudinal authority under lateral demand."""
    if fy_cap_total <= 1e-9:
        return 0.0
    ratio = float(fy_demand_total) / float(fy_cap_total)
    ratio = min(max(ratio, 0.0), 1.0)
    return float(np.sqrt(max(0.0, 1.0 - ratio * ratio)))


def _compute_corner_normal_load_state(vehicle, v_car, config):
    """Cornering solve load state (front/rear per-tyre) at approximately steady longitudinal accel."""
    return _compute_normal_loads_for_longitudinal(vehicle, v_car=v_car, a_long=0.0, config=config)


def _smooth_corner_speed_envelope(track, point_speeds, config):
    """
    Bound point-to-point speed cliffs in the corner envelope using finite accel/decel slopes.

    This only reduces local maxima and never raises point speeds, so curvature-derived lows are
    preserved while transition discontinuities are softened before forward/backward propagation.
    """
    solver_cfg = config.get('solver', {}) if isinstance(config, dict) else {}
    enabled = bool(solver_cfg.get('enable_corner_envelope_smoothing', False))
    try:
        max_decel_g = max(float(solver_cfg.get('corner_envelope_max_decel_g', 1.8)), 0.05)
    except (TypeError, ValueError):
        max_decel_g = 1.8
    try:
        max_accel_g = max(float(solver_cfg.get('corner_envelope_max_accel_g', 2.2)), 0.05)
    except (TypeError, ValueError):
        max_accel_g = 2.2
    try:
        max_iterations = int(solver_cfg.get('corner_envelope_smoothing_iterations', 2))
    except (TypeError, ValueError):
        max_iterations = 2
    max_iterations = max(1, min(max_iterations, 8))

    base = np.asarray(point_speeds, dtype=float)
    if (not enabled) or (base.size <= 1):
        diagnostics = {
            'corner_speed_smoothing_enabled': bool(enabled),
            'corner_speed_smoothing_max_decel_g': float(max_decel_g),
            'corner_speed_smoothing_max_accel_g': float(max_accel_g),
            'corner_speed_smoothing_iterations': 0,
            'corner_speed_smoothing_clamped_points': 0,
            'corner_speed_smoothing_max_reduction_mps': 0.0,
            'corner_speed_smoothing_mean_reduction_mps': 0.0,
        }
        return base.tolist(), diagnostics

    smoothed = np.maximum(base.copy(), 0.0)
    a_decel = float(max_decel_g) * 9.81
    a_accel = float(max_accel_g) * 9.81
    total_clamps = 0
    iterations_run = 0

    for _ in range(max_iterations):
        changed = 0

        for i in range(len(smoothed) - 2, -1, -1):
            ds = float(track.points[i + 1].distance - track.points[i].distance)
            if ds <= 0.0:
                continue
            max_prev = np.sqrt(max(smoothed[i + 1] ** 2 + 2.0 * a_decel * ds, 0.0))
            if smoothed[i] > max_prev:
                smoothed[i] = float(max_prev)
                changed += 1

        for i in range(1, len(smoothed)):
            ds = float(track.points[i].distance - track.points[i - 1].distance)
            if ds <= 0.0:
                continue
            max_curr = np.sqrt(max(smoothed[i - 1] ** 2 + 2.0 * a_accel * ds, 0.0))
            if smoothed[i] > max_curr:
                smoothed[i] = float(max_curr)
                changed += 1

        iterations_run += 1
        total_clamps += changed
        if changed == 0:
            break

    reduction = np.maximum(base - smoothed, 0.0)
    diagnostics = {
        'corner_speed_smoothing_enabled': True,
        'corner_speed_smoothing_max_decel_g': float(max_decel_g),
        'corner_speed_smoothing_max_accel_g': float(max_accel_g),
        'corner_speed_smoothing_iterations': int(iterations_run),
        'corner_speed_smoothing_clamped_points': int(total_clamps),
        'corner_speed_smoothing_max_reduction_mps': float(np.max(reduction)) if reduction.size else 0.0,
        'corner_speed_smoothing_mean_reduction_mps': float(np.mean(reduction)) if reduction.size else 0.0,
    }
    return smoothed.tolist(), diagnostics

def optimise_speed_at_points(track_points, vehicle, config):
    """
    Find maximum v_car at multiple track points where equilibrium states exist.
    Uses direct constrained optimization for each point.
    Effectively gives us max cornering speeds given our vehicle model.
    Args:
        track_points: List of track points with curvature data
        vehicle: Vehicle object
        config: Config dict
    Returns:
        point_speeds: List of maximum speeds for each point (m/s)
    """
    point_speeds = []
    solver_success = []
    fallback_used = []
    fallback_speed = []
    retry_count = []
    solve_method = []
    physical_cap_speed = []
    failure_reason = []
    tier_failure_reasons = []
    residual_lat_abs = []
    residual_yaw_abs = []
    residual_lat_rel = []
    residual_yaw_rel = []
    corner_front_normal_load_per_tyre = []
    corner_rear_normal_load_per_tyre = []
    corner_non_physical_normal_load = []
    corner_transfer_clamped = []
    straight_speed_cap = _get_straight_speed_cap(config)
    corner_max_bisection_iters = _get_corner_max_bisection_iters(config)
    previous_solution = None
    for point in track_points:
        curvature = point.curvature
        corner_load_state = _compute_corner_normal_load_state(vehicle, 20.0, config)
        corner_load_front = float(corner_load_state['front_per_tyre'])
        corner_load_rear = float(corner_load_state['rear_per_tyre'])
        corner_load_mean = float(corner_load_state['mean_per_tyre'])
        rollover_cap = _compute_rollover_speed_cap(curvature, vehicle)
        tyre_lateral_cap = _compute_tyre_lateral_speed_cap(curvature, vehicle, corner_load_mean, config)
        cap = float(straight_speed_cap)
        if np.isfinite(rollover_cap):
            cap = min(cap, float(rollover_cap))
        if np.isfinite(tyre_lateral_cap):
            cap = min(cap, float(tyre_lateral_cap))
        cap = max(0.0, float(cap))
        physical_cap_speed.append(float(cap))

        tiers = _build_retry_tiers(previous_solution, straight_speed_cap, rollover_cap)
        result = {'success': False, 'v_car': 0.0, 'a_steer': 0.0, 'a_sideslip': 0.0}
        used_method = 'none'
        attempts = 0
        per_tier_fail_reasons = []
        for tier in tiers:
            attempts += 1
            tier_result = find_vehicle_state_at_point(
                curvature,
                vehicle,
                normal_load_front_per_tyre=corner_load_front,
                normal_load_rear_per_tyre=corner_load_rear,
                straight_line_speed_cap=straight_speed_cap,
                initial_guess=tier.get('initial_guess'),
                v_upper_bound_mps=tier.get('v_upper_bound_mps'),
                max_bisection_iters=corner_max_bisection_iters,
            )
            if tier_result.get('success'):
                result = tier_result
                used_method = tier['name']
                break
            tier_reason = str(tier_result.get('failure_reason', 'unknown'))
            per_tier_fail_reasons.append(f"{tier['name']}:{tier_reason}")

        base_mu = getattr(vehicle.params, 'base_mu')
        if result['success']:
            logger.info(f"Optimized v_car: {result['v_car']:.2f} m/s for curvature={curvature:.4f}")
            point_speeds.append(result['v_car'])
            solver_success.append(True)
            fallback_used.append(False)
            fallback_speed.append(0.0)
            retry_count.append(max(0, attempts - 1))
            solve_method.append(used_method)
            failure_reason.append('none')
            tier_failure_reasons.append(';'.join(per_tier_fail_reasons))
            residual_lat_abs.append(float(result.get('residual_lat_abs', np.nan)))
            residual_yaw_abs.append(float(result.get('residual_yaw_abs', np.nan)))
            residual_lat_rel.append(float(result.get('residual_lat_rel', np.nan)))
            residual_yaw_rel.append(float(result.get('residual_yaw_rel', np.nan)))
            corner_load_state = _compute_normal_loads_for_longitudinal(vehicle, float(result['v_car']), 0.0, config)
            corner_front_normal_load_per_tyre.append(float(corner_load_state['front_per_tyre']))
            corner_rear_normal_load_per_tyre.append(float(corner_load_state['rear_per_tyre']))
            corner_non_physical_normal_load.append(bool(corner_load_state.get('non_physical_event', False)))
            corner_transfer_clamped.append(bool(corner_load_state.get('transfer_clamped', False)))
            previous_solution = {
                'v_car': float(result['v_car']),
                'a_steer': float(result['a_steer']),
                'a_sideslip': float(result['a_sideslip']),
            }
        else:
            logger.warning(f"Could not find equilibrium state for curvature={curvature:.4f}")
            logger.warning(f"This is point at coordinates x={point.x}, y={point.y}, z={point.z}")
            previous_speed = point_speeds[-1] if point_speeds else None
            v_fallback = _compute_constrained_fallback_speed(
                curvature=curvature,
                base_mu=base_mu,
                physical_cap_speed=cap,
                previous_speed=previous_speed,
                config=config,
            )
            logger.warning(f"Fallback: using v_fallback={v_fallback:.2f} m/s based on base_mu={base_mu}")
            point_speeds.append(v_fallback)
            solver_success.append(False)
            fallback_used.append(True)
            fallback_speed.append(v_fallback)
            retry_count.append(attempts)
            solve_method.append('fallback')
            if per_tier_fail_reasons:
                final_reason = per_tier_fail_reasons[-1].split(':', 1)[-1]
            else:
                final_reason = str(result.get('failure_reason', 'unknown'))
            failure_reason.append(final_reason)
            tier_failure_reasons.append(';'.join(per_tier_fail_reasons))
            residual_lat_abs.append(float(result.get('residual_lat_abs', np.nan)))
            residual_yaw_abs.append(float(result.get('residual_yaw_abs', np.nan)))
            residual_lat_rel.append(float(result.get('residual_lat_rel', np.nan)))
            residual_yaw_rel.append(float(result.get('residual_yaw_rel', np.nan)))
            corner_load_state = _compute_normal_loads_for_longitudinal(vehicle, float(v_fallback), 0.0, config)
            corner_front_normal_load_per_tyre.append(float(corner_load_state['front_per_tyre']))
            corner_rear_normal_load_per_tyre.append(float(corner_load_state['rear_per_tyre']))
            corner_non_physical_normal_load.append(bool(corner_load_state.get('non_physical_event', False)))
            corner_transfer_clamped.append(bool(corner_load_state.get('transfer_clamped', False)))
            previous_solution = None

    diagnostics = {
        'corner_solver_success': solver_success,
        'corner_fallback_used': fallback_used,
        'corner_fallback_speed': fallback_speed,
        'corner_retry_count': retry_count,
        'corner_solve_method': solve_method,
        'corner_physical_cap_speed': physical_cap_speed,
        'corner_failure_reason': failure_reason,
        'corner_tier_failure_reasons': tier_failure_reasons,
        'corner_solver_lat_residual_abs': residual_lat_abs,
        'corner_solver_yaw_residual_abs': residual_yaw_abs,
        'corner_solver_lat_residual_rel': residual_lat_rel,
        'corner_solver_yaw_residual_rel': residual_yaw_rel,
        'corner_front_normal_load_per_tyre': corner_front_normal_load_per_tyre,
        'corner_rear_normal_load_per_tyre': corner_rear_normal_load_per_tyre,
        'corner_non_physical_normal_load_events': int(sum(1 for x in corner_non_physical_normal_load if x)),
        'corner_normal_load_transfer_clamped_events': int(sum(1 for x in corner_transfer_clamped if x)),
    }
    return point_speeds, diagnostics

def forward_pass(track, vehicle, point_speeds, config):
    """
    Forward pass: acceleration-limited speed profile using powertrain model.
    Propagates speeds forward using available engine forces, capped by tyre
    longitudinal grip at a fixed wheel-slip operating point, minus drag.
    At each segment:
    - Select optimal gear for current speed
    - Compute available traction force from powertrain (F_x = T_wheel / r_wheel)
    - Cap traction by tyre longitudinal force at peak slip ratio
    - Subtract aerodynamic drag
    - Update speed via kinematics: v_pred = sqrt(v_prev^2 + 2 * a_lon * ds)
    Uses all track points.
    """
    n_points = len(track.points)
    speeds = np.zeros(n_points)
    speeds[0] = point_speeds[0]  # start at first point speed
    limiting_modes = ['initial'] * n_points
    primary_limiting_modes = ['initial'] * n_points
    powertrain_forces = [0.0] * n_points
    tyre_limit_forces = [0.0] * n_points
    tyre_lateral_caps = [0.0] * n_points
    combined_budget_scale = [1.0] * n_points
    net_long_forces = [0.0] * n_points
    normal_load_per_tyre = [vehicle.compute_static_normal_load()] * n_points
    front_normal_load_per_tyre = [vehicle.compute_static_normal_load()] * n_points
    rear_normal_load_per_tyre = [vehicle.compute_static_normal_load()] * n_points
    non_physical_normal_load_flags = [False] * n_points
    transfer_clamped_flags = [False] * n_points
    peak_slip_ratio = float(config.get('ab_testing', {}).get('peak_slip_ratio_accel', 12.0))

    for i in range(1, n_points):
        ds = track.points[i].distance - track.points[i-1].distance
        if ds <= 0:
            speeds[i] = speeds[i-1]
            limiting_modes[i] = 'degenerate_segment'
            primary_limiting_modes[i] = 'degenerate_segment'
            continue
        v_prev = speeds[i-1]
        v_calc = max(v_prev, 1.0)
        gear_ratio = vehicle.select_optimal_gear(v_calc)

        # Powertrain-limited wheel force at the contact patch.
        rpm = vehicle.speed_to_rpm(v_calc, gear_ratio)
        wheel_torque = vehicle.compute_wheel_torque(rpm, gear_ratio, throttle=1.0)
        f_traction_powertrain = wheel_torque / vehicle.params.wheel_radius

        # Estimate prior-step longitudinal acceleration for B1 load transfer coupling.
        a_long_est = 0.0
        if ds > 0.0:
            a_long_est = (v_calc**2 - v_prev**2) / (2.0 * ds)

        load_state = _compute_normal_loads_for_longitudinal(vehicle, v_calc, a_long_est, config)
        front_load = load_state['front_per_tyre']
        rear_load = load_state['rear_per_tyre']
        normal_load_per_tyre[i] = load_state['mean_per_tyre']
        front_normal_load_per_tyre[i] = float(front_load)
        rear_normal_load_per_tyre[i] = float(rear_load)
        non_physical_normal_load_flags[i] = bool(load_state.get('non_physical_event', False))
        transfer_clamped_flags[i] = bool(load_state.get('transfer_clamped', False))

        fx_cap_total, fy_cap_total = _compute_total_force_caps(
            vehicle=vehicle,
            front_load=front_load,
            rear_load=rear_load,
            config=config,
            peak_slip_ratio=peak_slip_ratio,
        )

        curvature = abs(track.points[i].curvature)
        # Budget lateral demand at physically feasible speed for this point.
        # Using uncapped v_calc can overstate lateral demand at corner entries.
        v_for_budget = min(v_calc, float(point_speeds[i]))
        fy_demand_total = vehicle.params.mass * (v_for_budget**2) * curvature
        budget_scale = _longitudinal_budget_scale_from_lateral_demand(fy_demand_total, fy_cap_total)
        f_traction_tyre_limit = fx_cap_total * budget_scale

        # Net longitudinal force after tyre slip limit and drag.
        f_traction = min(f_traction_powertrain, f_traction_tyre_limit)
        f_drag = vehicle.compute_aero_drag(v_calc)
        f_x = f_traction - f_drag

        powertrain_forces[i] = f_traction_powertrain
        tyre_limit_forces[i] = f_traction_tyre_limit
        tyre_lateral_caps[i] = fy_cap_total
        combined_budget_scale[i] = budget_scale
        net_long_forces[i] = f_x
        if f_traction_powertrain < f_traction_tyre_limit:
            primary_limiting_modes[i] = 'power_limited'
        else:
            primary_limiting_modes[i] = 'traction_limited'
        limiting_modes[i] = primary_limiting_modes[i]

        a_lon = f_x / vehicle.params.mass
        v_pred_squared = v_prev**2 + 2 * a_lon * ds
        if v_pred_squared < 0:
            v_pred = v_prev
        else:
            v_pred = np.sqrt(v_pred_squared)
        if v_pred > point_speeds[i]:
            limiting_modes[i] = 'corner_capped'
        v_pred = min(v_pred, point_speeds[i])
        speeds[i] = v_pred
    diagnostics = {
        'forward_limiting_mode': limiting_modes,
        'forward_primary_limiting_mode': primary_limiting_modes,
        'forward_powertrain_force': powertrain_forces,
        'forward_tyre_force_limit': tyre_limit_forces,
        'forward_tyre_lateral_cap': tyre_lateral_caps,
        'forward_combined_budget_scale': combined_budget_scale,
        'forward_net_long_force': net_long_forces,
        'forward_normal_load_per_tyre': normal_load_per_tyre,
        'forward_front_normal_load_per_tyre': front_normal_load_per_tyre,
        'forward_rear_normal_load_per_tyre': rear_normal_load_per_tyre,
        'forward_non_physical_normal_load_events': int(sum(1 for x in non_physical_normal_load_flags if x)),
        'forward_normal_load_transfer_clamped_events': int(sum(1 for x in transfer_clamped_flags if x)),
    }
    return speeds, diagnostics

def backward_pass(track, vehicle, point_speeds, config):
    """
    Backward pass: braking-limited speed profile using tyre model with friction circle.
    Propagates speeds backward from end to start. At each segment:
    - Compute peak longitudinal deceleration from tyre grip (a_limit = F_brake / mass)
    - Compute lateral acceleration demand at this point: a_lat = v^2 * curvature
    - Apply friction circle to find available longitudinal deceleration:
        a_long_available = sqrt(max(a_limit^2 - a_lat^2, 0))
      This ensures combined lateral + longitudinal demand never exceeds tyre capacity.
    - Add aerodynamic drag contribution
    - Work backwards: v_i = sqrt(v_{i+1}^2 + 2 * a_brake * ds)
    - Enforce v_i <= point_speeds[i] (corner limit)
    Uses all track points.
    """
    n_points = len(track.points)
    speeds = np.zeros(n_points)
    speeds[-1] = point_speeds[-1]
    limiting_modes = ['terminal'] * n_points
    brake_force_limits = [0.0] * n_points
    brake_decel_limits_raw = [0.0] * n_points
    brake_decel_limits = [0.0] * n_points
    brake_lateral_caps = [0.0] * n_points
    brake_combined_budget_scale = [1.0] * n_points
    brake_decel_capped = [False] * n_points
    normal_load_per_tyre = [vehicle.compute_static_normal_load()] * n_points
    front_normal_load_per_tyre = [vehicle.compute_static_normal_load()] * n_points
    rear_normal_load_per_tyre = [vehicle.compute_static_normal_load()] * n_points
    non_physical_normal_load_flags = [False] * n_points
    transfer_clamped_flags = [False] * n_points
    peak_slip_ratio = float(config.get('ab_testing', {}).get('peak_slip_ratio_brake', 12.0))
    solver_cfg = config.get('solver', {}) if isinstance(config, dict) else {}
    max_brake_decel_g_cfg = solver_cfg.get('max_brake_decel_g', None)
    max_brake_decel_mps2 = np.inf
    if max_brake_decel_g_cfg is not None:
        try:
            max_brake_decel_mps2 = max(0.0, float(max_brake_decel_g_cfg)) * 9.81
        except (TypeError, ValueError):
            max_brake_decel_mps2 = np.inf

    for i in range(n_points-2, -1, -1):
        ds = track.points[i+1].distance - track.points[i].distance
        if ds <= 0:
            speeds[i] = speeds[i+1]
            limiting_modes[i] = 'degenerate_segment'
            continue
        v_next = speeds[i+1]

        # Positive a_long here is deceleration demand in backward pass approximation.
        a_long_est = (max(v_next, 0.0) ** 2) / (2.0 * max(ds, 1e-6))
        load_state = _compute_normal_loads_for_longitudinal(vehicle, v_next, -a_long_est, config)
        front_load = load_state['front_per_tyre']
        rear_load = load_state['rear_per_tyre']
        normal_load_per_tyre[i] = load_state['mean_per_tyre']
        front_normal_load_per_tyre[i] = float(front_load)
        rear_normal_load_per_tyre[i] = float(rear_load)
        non_physical_normal_load_flags[i] = bool(load_state.get('non_physical_event', False))
        transfer_clamped_flags[i] = bool(load_state.get('transfer_clamped', False))

        fx_cap_total, fy_cap_total = _compute_total_force_caps(
            vehicle=vehicle,
            front_load=front_load,
            rear_load=rear_load,
            config=config,
            peak_slip_ratio=-peak_slip_ratio,
        )

        # Lateral acceleration demanded at this point by the corner geometry (m/s^2)
        curvature = abs(track.points[i].curvature)
        a_lat = v_next**2 * curvature

        fy_demand_total = vehicle.params.mass * a_lat
        budget_scale = _longitudinal_budget_scale_from_lateral_demand(fy_demand_total, fy_cap_total)
        f_brake_total = fx_cap_total * budget_scale

        # Peak longitudinal deceleration available from tyres (m/s^2)
        a_limit = f_brake_total / vehicle.params.mass

        # Friction circle: longitudinal budget is reduced by lateral demand.
        # a_long^2 + a_lat^2 <= a_limit^2  =>  a_long = sqrt(a_limit^2 - a_lat^2)
        a_lat_clamped = min(a_lat, a_limit)  # cannot exceed total limit
        a_brake = np.sqrt(max(a_limit**2 - a_lat_clamped**2, 0.0))

        # Add aerodynamic drag (acts as free braking, outside friction circle)
        f_drag = vehicle.compute_aero_drag(v_next)
        a_brake += f_drag / vehicle.params.mass
        a_brake_raw = float(a_brake)
        if np.isfinite(max_brake_decel_mps2) and a_brake_raw > max_brake_decel_mps2:
            a_brake = float(max_brake_decel_mps2)
            brake_decel_capped[i] = True
        brake_force_limits[i] = f_brake_total
        brake_decel_limits_raw[i] = a_brake_raw
        brake_decel_limits[i] = a_brake
        brake_lateral_caps[i] = fy_cap_total
        brake_combined_budget_scale[i] = budget_scale
        if a_lat_clamped >= a_limit * 0.99:
            limiting_modes[i] = 'lateral_saturated'
        else:
            limiting_modes[i] = 'brake_limited'

        v_brake_squared = v_next**2 + 2 * a_brake * ds
        if v_brake_squared < 0:
            v_brake = v_next
        else:
            v_brake = np.sqrt(v_brake_squared)
        if v_brake > point_speeds[i]:
            limiting_modes[i] = 'corner_capped'
        speeds[i] = min(v_brake, point_speeds[i])

    diagnostics = {
        'backward_limiting_mode': limiting_modes,
        'backward_brake_force_limit': brake_force_limits,
        'backward_brake_decel_limit_raw': brake_decel_limits_raw,
        'backward_brake_decel_limit': brake_decel_limits,
        'backward_tyre_lateral_cap': brake_lateral_caps,
        'backward_combined_budget_scale': brake_combined_budget_scale,
        'backward_brake_decel_capped': brake_decel_capped,
        'backward_brake_decel_cap_applied_events': int(sum(1 for x in brake_decel_capped if x)),
        'backward_normal_load_per_tyre': normal_load_per_tyre,
        'backward_front_normal_load_per_tyre': front_normal_load_per_tyre,
        'backward_rear_normal_load_per_tyre': rear_normal_load_per_tyre,
        'backward_non_physical_normal_load_events': int(sum(1 for x in non_physical_normal_load_flags if x)),
        'backward_normal_load_transfer_clamped_events': int(sum(1 for x in transfer_clamped_flags if x)),
    }
    return speeds, diagnostics

def compute_speed_profile(track, vehicle, config):
    """
    Compute final speed profile using forward and backward passes for all track points.
    Parallelises the optimisation of cornering speeds at each point.
    """
    if hasattr(vehicle, 'tyre_model') and hasattr(vehicle.tyre_model, 'reset_domain_diagnostics'):
        vehicle.tyre_model.reset_domain_diagnostics()

    # Pass 1: Find ultimate speeds possible given vehicle model
    point_speeds_raw, corner_diag = optimise_speed_at_points(track.points, vehicle, config)
    point_speeds, smoothing_diag = _smooth_corner_speed_envelope(track, point_speeds_raw, config)
    # Pass 2: Forward pass propagating accel limits
    forward_speeds, forward_diag = forward_pass(track, vehicle, point_speeds, config)
    # Pass 3: Backward pass propagating decel limits
    backward_speeds, backward_diag = backward_pass(track, vehicle, point_speeds, config)

    # Take minimum of forward and backward speeds to get final speed profile
    final_speeds = np.minimum(forward_speeds, backward_speeds)
    diagnostics = {
        **corner_diag,
        **smoothing_diag,
        **forward_diag,
        **backward_diag,
        'model_variant': _get_model_variant(config),
        'scenario': _get_scenario_context(config),
    }
    diagnostics['normal_load_non_physical_events_total'] = int(
        diagnostics.get('corner_non_physical_normal_load_events', 0)
        + diagnostics.get('forward_non_physical_normal_load_events', 0)
        + diagnostics.get('backward_non_physical_normal_load_events', 0)
    )
    diagnostics['normal_load_transfer_clamped_events_total'] = int(
        diagnostics.get('corner_normal_load_transfer_clamped_events', 0)
        + diagnostics.get('forward_normal_load_transfer_clamped_events', 0)
        + diagnostics.get('backward_normal_load_transfer_clamped_events', 0)
    )
    if hasattr(vehicle, 'tyre_model') and hasattr(vehicle.tyre_model, 'get_domain_diagnostics'):
        diagnostics['tyre_domain'] = vehicle.tyre_model.get_domain_diagnostics()
    return final_speeds, point_speeds, diagnostics
