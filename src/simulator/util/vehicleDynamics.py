import numpy as np
import logging
from scipy.optimize import root
from scipy.constants import g
from typing import Optional, Dict

logger = logging.getLogger(__name__)

def compute_v_car_max(g_lat: float, curvature: float) -> float:
    """
    Compute maximum theoretical speed for a given lateral acceleration and track curvature.
    v_max = sqrt(a_lat / curvature)
    Args:
        g_lat: Lateral acceleration in m/s^2
        curvature: Track curvature in 1/m
    Returns:
        Maximum speed in m/s
    """
    v_car_max = np.sqrt(abs(g_lat) / abs(curvature))   # m/s
    return v_car_max

def estimate_roll_angle(v_car: float, a_steer: float, a_sideslip: float, curvature: float, vehicle, debug_mode=False):
    """
    Conservative roll angle estimate (rad) from lateral load transfer:
      roll_angle = roll_moment / roll_stiffness
    Returns (roll_angle_rad, margin) where margin = max_roll_angle_rad - abs(roll_angle_rad).
    """
    params = getattr(vehicle, 'params', None)
    mass = getattr(params, 'mass', 1500.0)
    cog_z = getattr(params, 'cog_z', getattr(params, 'cog_z'))
    roll_stiffness = getattr(params, 'roll_stiffness')  # Nm/rad total
    max_roll_angle_deg = getattr(params, 'max_roll_angle_deg')  # degrees allowed before fail
    max_roll_angle_rad = np.deg2rad(max_roll_angle_deg)

    # lateral acceleration (use curvature if present)
    try:
        g_lat = (v_car**2) * curvature
    except Exception:
        g_lat = 0.0
    g_lat = float(abs(g_lat))

    F_lat = mass * g_lat
    roll_moment = F_lat * cog_z
    roll_angle = roll_moment / max(1e-12, roll_stiffness)

    margin = max_roll_angle_rad - abs(roll_angle)
    if debug_mode:
        print(f"[DEBUG][roll] v={v_car:.2f} g_lat={g_lat:.2f} roll_angle={roll_angle:.4f} rad "
              f"max={max_roll_angle_rad:.4f} margin={margin:.4f}")
    return roll_angle, margin
    
def estimate_effective_cog_z(v_car: float, a_steer: float, a_sideslip: float, curvature: float, vehicle, debug_mode) -> tuple:
    """
    Estimate effective CoG z (meters) after roll and aero-induced suspension compression.
    Returns (feasible: bool, cog_z_est: float, margin: float) where margin = max_CoG_z - cog_z_est.
    Uses vehicle.params.* when available, otherwise falls back to conservative defaults.
    """

    params = getattr(vehicle, 'params', None)
    mass = getattr(params, 'mass')                      # kg
    roll_stiffness = getattr(params, 'roll_stiffness')  # Nm/rad total
    max_CoG_z = getattr(params, 'max_cog_z')            # m
    cog_z = getattr(params, 'cog_z')                    # m
    track = getattr(params, 'rear_track_width')         # m

    # compute lateral acceleration (m/s^2) (use curvature based if available)
    try:
        g_lat = (v_car**2) * curvature
    except Exception:
        g_lat = 0.0
    g_lat = float(abs(g_lat))

    # lateral force and roll moment
    F_lat = mass * g_lat                    # N
    roll_moment = F_lat * cog_z             # Nm (approx, lever = cog_z)

    # approximate roll angle (rad) and resulting vertical compression (heuristic)
    roll_angle = roll_moment / max(1e-12, roll_stiffness)   # rad
    # vertical displacement due to roll: approximate using small-angle geometry
    # assume one side compresses roughly by track/2 * sin(roll_angle) -> use absolute value
    delta_h_roll = abs((track / 2.0) * np.sin(roll_angle))

    # total estimated lowering of CoG
    cog_z_est = cog_z - (delta_h_roll)
    # safety clamp (don't go negative)
    cog_z_est = float(max(0.0, cog_z_est))

    margin = max_CoG_z - cog_z_est
    feasible = (cog_z_est <= max_CoG_z)

    return feasible, cog_z_est, margin

def evaluate_vehicle_state(v_car: float, a_steer: float, a_sideslip: float, curvature: float, vehicle, debug_mode) -> dict:
    """
    Evaluate vehicle state for given v_car, a_steer, a_sideslip, and track curvature.
    Args:
        v_car: Vehicle speed (m/s)
        a_steer: Steering angle (degrees)
        a_sideslip: Sideslip angle (degrees)
        curvature: Track curvature (1/m)
        vehicle: Vehicle object
        debug_mode: Debug mode flag
    Returns:
        dict: {'g_lat': float, 'm_z': float, 'is_valid': bool, 'f_front': float, 'f_rear': float}
    """
    slip_angle_front = a_steer - a_sideslip
    slip_angle_rear = -a_sideslip
    f_front, f_rear = vehicle.compute_tyre_forces(slip_angle_front, slip_angle_rear)
    m_z = vehicle.compute_yaw_moment(f_front, f_rear, a_steer)
    g_lat = vehicle.compute_lateral_acceleration(f_front, f_rear, v_car)
    is_valid = abs(m_z) < 50.0
    if debug_mode:
        print(f"[DEBUG] variables: v_car={v_car:.2f}, g_lat={g_lat:.2f}, m_z={m_z:.2f}, is_valid={is_valid}, f_front={f_front:.2f}, f_rear={f_rear:.2f}")
    return {
        'g_lat': g_lat,
        'm_z': m_z,
        'is_valid': is_valid,
        'f_front': f_front,
        'f_rear': f_rear
    }

def find_vehicle_state_at_point(
    curvature: float,
    vehicle,
    normal_load_per_tyre: float = None,
    normal_load_front_per_tyre: float = None,
    normal_load_rear_per_tyre: float = None,
    straight_line_speed_cap: float = 200.0,
    initial_guess: Optional[Dict[str, float]] = None,
    v_upper_bound_mps: Optional[float] = None,
    max_bisection_iters: int = 30,
):
    """
    Find the maximum feasible steady-state cornering state at a single track point.

    This routine solves a quasi-static bicycle-model equilibrium for a given track
    curvature by:
    1) Bracketing vehicle speed with bisection.
    2) Solving steering angle and sideslip angle at each speed candidate using
       a nonlinear root solve.
    3) Keeping the highest speed that satisfies force/moment equilibrium and
       basic state sanity checks.

    Equilibrium equations solved at each bisection speed `v_mid`:
    - Lateral force balance:
      `m * v_mid^2 * K = Fy_f + Fy_r`
    - Yaw moment balance about CoG:
      `a * Fy_f = b * Fy_r`

    Slip-angle model (small-angle bicycle form):
    - `alpha_f = delta - beta - a*K`
    - `alpha_r = -beta + b*K`

    Where:
    - `K` is track curvature [1/m]
    - `delta` is steering angle [rad] inside the solver
    - `beta` is vehicle sideslip [rad] inside the solver
    - `a`, `b` are CoG-to-axle distances [m]

    Notes:
    - Tyre model API expects slip angles in degrees, so `alpha_f/alpha_r` are
      converted before force lookup.
    - A root-solver success flag alone is not sufficient; residual magnitudes are
      also checked before accepting a state.
    - For near-straight segments (`|curvature| < 1e-4`), the function returns a
      fixed high-speed placeholder with zero steer/sideslip.

    Args:
        curvature: Local track curvature in 1/m. Sign indicates turn direction.
        vehicle: Vehicle model instance. Must expose:
            - `params` with at least `mass`, `wheelbase`, `front_track_width`,
              `cog_z`, and `cog_longitudinal_pos`
            - `compute_tyre_forces(front_slip_deg, rear_slip_deg)` returning
              axle lateral forces in N.

    Returns:
        dict:
            - `success` (bool): True if at least one feasible equilibrium was found.
            - `v_car` (float): Maximum feasible speed at this curvature [m/s].
            - `a_steer` (float): Steering angle at `v_car` [deg].
            - `a_sideslip` (float): Vehicle sideslip angle at `v_car` [deg].

        If no feasible equilibrium is found, returns `success=False` with zeros
        for the state values.
    """
    
    # Handle straight sections (avoid division by zero)
    if abs(curvature) < 1e-4:
        v_straight = float(straight_line_speed_cap)
        if v_upper_bound_mps is not None and np.isfinite(v_upper_bound_mps):
            v_straight = min(v_straight, float(v_upper_bound_mps))
        return {
            'success': True,
            'v_car': max(0.0, v_straight),
            'a_steer': 0.0,
            'a_sideslip': 0.0,
            'failure_reason': 'none',
            'residual_lat_abs': 0.0,
            'residual_yaw_abs': 0.0,
            'residual_lat_rel': 0.0,
            'residual_yaw_rel': 0.0,
        }
    

    # Step 1: set params
    p = getattr(vehicle, 'params', None)
    m = getattr(p, 'mass', 300.0)
    L = getattr(p, 'wheelbase', 1.53)
    t = getattr(p, 'front_track_width', 1.20)
    h = getattr(p, 'cog_z', 0.28)
    
    # cog_longitudinal_pos = front mass fraction = l_r / L (distance rear-to-CoG over wheelbase).
    # So b = l_r (CoG to rear axle) and a = l_f (CoG to front axle).
    wd_f = getattr(p, 'cog_longitudinal_pos', 0.46)

    # Calculate axle distances
    b = L * wd_f      # l_r: distance from CoG to rear axle (m)
    a = L - b         # l_f: distance from CoG to front axle (m)
    
    # Track params
    K = curvature
    R = 1.0 / abs(K)

    # Step 2 Initial guess
    
    # Rollover limit
    v_rollover = np.sqrt((t / (2 * h)) * g * R)
    
    # Always enforce rollover cap to keep cornering bounds physically realistic.
    v_bound = min(v_rollover, float(straight_line_speed_cap))

    if v_upper_bound_mps is not None and np.isfinite(v_upper_bound_mps):
        v_bound = min(float(v_bound), float(v_upper_bound_mps))
    v_bound = max(0.0, float(v_bound))
    if v_bound <= 0.0:
        return {
            'success': False,
            'v_car': 0.0,
            'a_steer': 0.0,
            'a_sideslip': 0.0,
            'failure_reason': 'invalid_speed_bound',
            'residual_lat_abs': np.nan,
            'residual_yaw_abs': np.nan,
            'residual_lat_rel': np.nan,
            'residual_yaw_rel': np.nan,
        }
    
    # Bicycle model: delta approx L * K
    guess_delta = np.arctan(L * K)
    guess_beta = 0.0
    if isinstance(initial_guess, dict):
        try:
            guess_delta = np.radians(float(initial_guess.get('a_steer', np.degrees(guess_delta))))
            guess_beta = np.radians(float(initial_guess.get('a_sideslip', 0.0)))
        except (TypeError, ValueError):
            guess_delta = np.arctan(L * K)
            guess_beta = 0.0

    # step 3: Bisection bounds
    v_low = 0.0
    v_high = v_bound
    
    # Store the best solution found
    final_result = {
        'success': False,
        'v_car': 0.0,
        'a_steer': 0.0,
        'a_sideslip': 0.0,
        'failure_reason': 'no_feasible_solution',
        'residual_lat_abs': np.nan,
        'residual_yaw_abs': np.nan,
        'residual_lat_rel': np.nan,
        'residual_yaw_rel': np.nan,
    }
    last_failure_reason = 'no_feasible_solution'
    last_residual_lat_abs = np.nan
    last_residual_yaw_abs = np.nan
    last_residual_lat_rel = np.nan
    last_residual_yaw_rel = np.nan

    # Bisection search 
    for _ in range(max(1, int(max_bisection_iters))):
        v_mid = (v_low + v_high) / 2.0
        
        # --- Step 4: Solver (Inner Loop: Root finding for delta, beta) ---
        
        def residuals(x):
            # x[0] = delta (steering), x[1] = beta (sideslip)
            delta, beta = x
            
            # Calculate Slip Angles - Step 3.ii
            # Front: alpha_f = delta - beta - aK
            alpha_f = delta - beta - (a * K)
            
            # Rear: alpha_r = -beta + bK
            alpha_r = -beta + (b * K)
            
            # Tyre model expects degrees.
            if (normal_load_front_per_tyre is None) and (normal_load_rear_per_tyre is None):
                if normal_load_per_tyre is None:
                    Fy_f, Fy_r = vehicle.compute_tyre_forces(np.degrees(alpha_f), np.degrees(alpha_r))
                else:
                    Fy_f, Fy_r = vehicle.compute_tyre_forces(
                        np.degrees(alpha_f),
                        np.degrees(alpha_r),
                        normal_load_front=normal_load_per_tyre,
                        normal_load_rear=normal_load_per_tyre,
                    )
            else:
                front_load = normal_load_front_per_tyre if normal_load_front_per_tyre is not None else normal_load_per_tyre
                rear_load = normal_load_rear_per_tyre if normal_load_rear_per_tyre is not None else normal_load_per_tyre
                Fy_f, Fy_r = vehicle.compute_tyre_forces(
                    np.degrees(alpha_f),
                    np.degrees(alpha_r),
                    normal_load_front=front_load,
                    normal_load_rear=rear_load,
                )
            
            # Equations to solve - Step 4.iii 
            # Lateral Force Balance: m*v^2*K - (Fy_f + Fy_r) = 0
            res_lat = (m * (v_mid**2) * K) - (Fy_f + Fy_r)
            
            # Yaw Moment Equilibrium: a*Fy_f - b*Fy_r = 0
            res_yaw = (a * Fy_f) - (b * Fy_r)
            
            return [res_lat, res_yaw]

        # Use Scipy's root finder (hybr or lm)
        sol = root(residuals, [guess_delta, guess_beta], method='lm', tol=1e-4)
        
        # Check if a physically valid solution exists
        if sol.success:
            
            delta_sol, beta_sol = sol.x
            res_lat, res_yaw = residuals(sol.x)
            # Keep checks scale-aware.
            lat_scale = max(1.0, abs(m * (v_mid**2) * K))
            yaw_scale = max(1.0, lat_scale * max(a, b))
            res_lat_abs = float(abs(res_lat))
            res_yaw_abs = float(abs(res_yaw))
            res_lat_rel = float(res_lat_abs / lat_scale)
            res_yaw_rel = float(res_yaw_abs / yaw_scale)
            last_residual_lat_abs = res_lat_abs
            last_residual_yaw_abs = res_yaw_abs
            last_residual_lat_rel = res_lat_rel
            last_residual_yaw_rel = res_yaw_rel
            residual_ok = (abs(res_lat) <= 1e-2 * lat_scale) and (abs(res_yaw) <= 1e-2 * yaw_scale)
            
            # Basic check (e.g. < 45 degrees)
            if residual_ok and abs(delta_sol) < 0.8 and abs(beta_sol) < 0.8:
                # speed is feasible.
                # Update bounds to search upper half
                v_low = v_mid
                
                # Save as current best
                final_result = {
                    'success': True,
                    'v_car': v_mid,
                    'a_steer': np.degrees(delta_sol),
                    'a_sideslip': np.degrees(beta_sol),
                    'failure_reason': 'none',
                    'residual_lat_abs': res_lat_abs,
                    'residual_yaw_abs': res_yaw_abs,
                    'residual_lat_rel': res_lat_rel,
                    'residual_yaw_rel': res_yaw_rel,
                }
                
                # Use this solution as the guess for the next higher speed (Step 4 note)
                guess_delta = delta_sol
                guess_beta = beta_sol
            else:
                # Converged to bs
                v_high = v_mid
                if not residual_ok:
                    last_failure_reason = 'residual_not_met'
                else:
                    last_failure_reason = 'state_bounds_exceeded'
        else:
            # Solver failed to find equilibrium, car cannot corner at this speed
            v_high = v_mid
            last_failure_reason = 'root_failed'

    if not final_result['success']:
        final_result['failure_reason'] = last_failure_reason
        final_result['residual_lat_abs'] = last_residual_lat_abs
        final_result['residual_yaw_abs'] = last_residual_yaw_abs
        final_result['residual_lat_rel'] = last_residual_lat_rel
        final_result['residual_yaw_rel'] = last_residual_yaw_rel

    return final_result
