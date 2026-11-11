import sys
import os
import numpy as np
import logging
import json
import matplotlib.pyplot as plt

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))

# Add src to path
sys.path.append(os.path.join(REPO_ROOT, "src"))

from vehicle.vehicle import create_vehicle
from track.track import Track, load_track
from simulator.util.prettyGraphs.lapTimeResults import plot_lap_time_results, LapTimeResults

"""
This script uses a simplified approach to simulate a straight-line acceleration test.
It replaces the three-pass lap time simulation with a single forward pass that
incorporates traction limits.

The vehicle accelerates from 0 to maximum speed on a straight track, taking the minimum of the
powertrain limits (max possible tractive force on ground given powertrain) and traction limits 
(based on longitudinal potential of tyre model and normal load on driven wheels).

Assumptions:
- Straight track with no corners.
- High point speed limits (e.g., 300 m/s) to avoid limiting acceleration.
- Traction limit is calculated based on rear axle load (assuming RWD for simplicity).
"""

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def traction_limited_forward_pass(track, vehicle, point_speeds, reaction_time, shift_time=0.15):
    """
    Forward pass with traction limitation.
    """
    n_points = len(track.points)
    speeds = np.zeros(n_points)
    speeds[0] = point_speeds[0]  # start at first point speed (0)
    
    # Data logging
    log_data = {
        'distance': [],
        'velocity': [],
        'rpm': [],
        'slip_ratio': [],
        'normal_load': [],
        'gear': []
    }
    
    # Assume RWD for traction limit (conservative for FS)
    # If the car is AWD, this would need to be adjusted.
    # We will calculate load on rear axle.
    
    current_gear = vehicle.select_optimal_gear(0.1)
    shift_timer = 0.0
    
    for i in range(1, n_points):
        ds = track.points[i].distance - track.points[i-1].distance
        if ds <= 0:
            speeds[i] = speeds[i-1]
            continue
            
        v_prev = speeds[i-1]
        v_calc = max(v_prev, 0.1) # Avoid zero division
        
        # Gear Selection & Shift Logic
        optimal_gear = vehicle.select_optimal_gear(v_calc)
        
        # Detect shift
        if optimal_gear != current_gear and shift_timer <= 0:
            shift_timer = shift_time
            current_gear = optimal_gear
            
        # 1. Powertrain Limit
        rpm = vehicle.speed_to_rpm(v_calc, current_gear)
        
        # Clutch slip simulation for launch
        # If RPM is too low, assume we are slipping clutch at launch_rpm
        launch_rpm = 6000.0 
        effective_rpm = max(rpm, launch_rpm)
        
        if shift_timer > 0:
            # Lull period - coasting
            wheel_torque = 0.0
            # Decrement timer based on estimated time for this step
            dt_step = ds / v_calc
            shift_timer -= dt_step
        else:
            wheel_torque = vehicle.compute_wheel_torque(effective_rpm, current_gear, throttle=1.0)
        
        if i < 5:
             logger.info(f"Point {i}: v_prev={v_prev:.3f}, v_calc={v_calc:.3f}, rpm={rpm:.1f}, eff_rpm={effective_rpm:.1f}, wheel_torque={wheel_torque:.1f}")

        # Convert to tractive force at wheels
        f_powertrain_total = wheel_torque / vehicle.params.wheel_radius
        
        # 2. Traction Limit
        # We need to solve for acceleration 'a' such that F_traction <= F_grip
        # F_grip depends on Normal Load, which depends on 'a'.
        # F_z_rear = F_z_static_rear + F_aero_rear + Delta_F_z
        # Delta_F_z = (m * a * h_cg) / L
        
        # Static Load
        weight = vehicle.params.mass * 9.81
        w_rear = weight * vehicle.params.cog_longitudinal_pos
        f_z_static_rear = w_rear # Total rear axle load
        
        # Aero Load
        f_downforce = vehicle.compute_downforce(v_calc)
        # Distribute downforce based on CP. 
        # aero_cp is distance from front axle.
        # fraction_rear = aero_cp / wheelbase
        aero_fraction_rear = vehicle.params.aero_centre_of_pressure / vehicle.params.wheelbase
        f_aero_rear = f_downforce * aero_fraction_rear
        
        # We need to find 'a' (acceleration).
        # a = (F_tractive - F_drag) / m
        # F_tractive = min(F_powertrain_total, F_grip)
        
        # Let's iterate to find consistent 'a' and 'F_grip'
        # Initial guess: a based on powertrain only
        f_drag = vehicle.compute_aero_drag(v_calc)
        a_guess = (f_powertrain_total - f_drag) / vehicle.params.mass
        
        # Iteration parameters
        max_iter = 5
        
        # Peak slip ratio for acceleration (assumed similar to braking or from config)
        peak_slip = 12.0 # Using the value from backward_pass
        
        final_a = a_guess
        final_f_grip_total = 0.0
        final_f_z_rear_tyre = 0.0
        
        for _ in range(max_iter):
            # Calculate Load Transfer
            delta_f_z = (vehicle.params.mass * final_a * vehicle.params.cog_z) / vehicle.params.wheelbase
            
            # Total Rear Load (RWD assumption)
            f_z_rear_total = f_z_static_rear + f_aero_rear + delta_f_z
            
            # Per tyre load (2 rear tyres)
            f_z_rear_tyre = f_z_rear_total / 2.0
            final_f_z_rear_tyre = f_z_rear_tyre
            
            # Get max grip from tyre model
            # Note: get_longitudinal_force might return negative for braking, we want magnitude
            # We pass positive slip for acceleration if the model supports it, or just magnitude
            # The backward pass used negative slip. Let's try positive.
            f_grip_tyre = vehicle.tyre_model.get_longitudinal_force(slip_ratio=peak_slip, normal_load=f_z_rear_tyre)
            f_grip_total = f_grip_tyre * 2.0
            final_f_grip_total = f_grip_total
            
            # Actual Tractive Force
            f_tractive = min(f_powertrain_total, f_grip_total)
            
            # New Acceleration
            new_a = (f_tractive - f_drag) / vehicle.params.mass
            
            if abs(new_a - final_a) < 0.01:
                final_a = new_a
                break
            
            final_a = new_a
            
        # 3. Propagate Speed
        a_lon = final_a
        v_pred_squared = v_prev**2 + 2 * a_lon * ds
        
        if v_pred_squared < 0:
            v_pred = v_prev
        else:
            v_pred = np.sqrt(v_pred_squared)
            
        # Clamp to point speed limit (though for straight line it's high)
        v_pred = min(v_pred, point_speeds[i])
        
        speeds[i] = v_pred
        
        # Estimate Slip Ratio for logging
        current_slip = 0.0
        if f_powertrain_total >= final_f_grip_total:
            current_slip = peak_slip
        else:
            # Simple linear estimation if not traction limited (0 to peak_slip)
            # This is an approximation as we don't have the inverse function
            ratio = max(0, f_powertrain_total) / max(1.0, final_f_grip_total)
            current_slip = ratio * peak_slip
            
        # Log Data
        log_data['distance'].append(track.points[i].distance)
        log_data['velocity'].append(v_pred)
        log_data['rpm'].append(rpm)
        log_data['slip_ratio'].append(current_slip)
        log_data['normal_load'].append(final_f_z_rear_tyre)
        log_data['gear'].append(current_gear)
        
    return speeds, log_data

def main():
    # Load Config
    config_path = os.path.join(REPO_ROOT, "config.json")
    with open(config_path, 'r') as f:
        config = json.load(f)
    
    # Create Vehicle
    vehicle = create_vehicle(config)
    
    # Load Track
    track_path = os.path.join(REPO_ROOT, config['track']['file_path'])
    track = load_track(track_path, debug_mode=False)
    
    logger.info(f"Track loaded: {len(track.points)} points")
    
    # Setup Point Speeds (Pass 1 replacement)
    # Exclude first pass: just set high limits, but 0 at start
    point_speeds = np.full(len(track.points), 300.0) # 300 m/s limit
    point_speeds[0] = 0.0
    
    # Run Forward Pass (Pass 2 replacement with traction)
    logger.info("Running Traction Limited Forward Pass...")
    reaction_time = 0.25
    final_speeds, log_data = traction_limited_forward_pass(track, vehicle, point_speeds, reaction_time=reaction_time)
    
    # Exclude Backward Pass (Pass 3): We just use the forward pass results
    # But we need 'corner_speeds' for the results object. We can just use point_speeds.
    
    # Compute Lap Time
    lap_time = 0.0
    g_lat_channel = []
    g_long_channel = []
    normal_load_per_tyre = [] # Placeholder
    long_force_per_tyre = [] # Placeholder
    lat_force_per_tyre = [] # Placeholder
    
    for i in range(1, len(track.points)):
        ds = track.points[i].distance - track.points[i-1].distance
        v_prev = final_speeds[i-1]
        v_curr = final_speeds[i]
        v_avg = (v_curr + v_prev) / 2
        
        if ds > 0:
            g_long = ((v_curr**2 - v_prev**2) / (2 * ds)) / 9.81
        else:
            g_long = 0.0
        g_long_channel.append(g_long)
        
        # Lateral G (should be 0 for straight line)
        g_lat = v_curr**2 * track.points[i].curvature / 9.81
        g_lat_channel.append(g_lat)
        
        if v_avg > 0:
            dt = ds / v_avg
            lap_time += dt
            
    # Add reaction time
    lap_time += reaction_time
            
    logger.info(f"Estimated 0-Max Speed Time (incl. {reaction_time}s reaction): {lap_time:.2f} seconds")
    logger.info(f"Max Speed Reached: {np.max(final_speeds):.2f} m/s ({np.max(final_speeds)*3.6:.2f} kph)")

    # Plot Results
    # 1. Standard Lap Time Results
    results = LapTimeResults(
        track=track,
        final_speeds=np.array(final_speeds),
        corner_speeds=np.array(point_speeds),
        lap_time=lap_time,
        g_lat_channel=g_lat_channel,
        g_long_channel=g_long_channel,
        normal_load_per_tyre=normal_load_per_tyre,
        long_force_per_tyre=long_force_per_tyre,
        lat_force_per_tyre=lat_force_per_tyre,
    )
    
    plot_lap_time_results(results)
    
    # Custom Plots
    fig, axs = plt.subplots(4, 1, figsize=(10, 12), sharex=True)
    
    # Velocity
    axs[0].plot(log_data['distance'], np.array(log_data['velocity']) * 3.6, label='Velocity (kph)')
    axs[0].set_ylabel('Velocity (kph)')
    axs[0].grid(True)
    axs[0].legend()
    
    # RPM
    axs[1].plot(log_data['distance'], log_data['rpm'], label='RPM', color='orange')
    axs[1].set_ylabel('RPM')
    axs[1].grid(True)
    axs[1].legend()
    
    # Slip Ratio
    axs[2].plot(log_data['distance'], log_data['slip_ratio'], label='Slip Ratio (%)', color='green')
    axs[2].set_ylabel('Slip Ratio (%)')
    axs[2].grid(True)
    axs[2].legend()
    
    # Normal Load
    axs[3].plot(log_data['distance'], log_data['normal_load'], label='Rear Tyre Normal Load (N)', color='red')
    axs[3].set_ylabel('Normal Load (N)')
    axs[3].set_xlabel('Distance (m)')
    axs[3].grid(True)
    axs[3].legend()
    
    plt.tight_layout()
    plt.show()

if __name__ == "__main__":
    main()
