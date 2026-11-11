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

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_range_test(vehicle, power_limit_kw, energy_target_kwh, dt=0.05):
    """
    Simulate a straight line run with a power limit until energy is depleted.
    
    Args:
        vehicle: Vehicle object
        power_limit_kw: Maximum power output allowed (kW)
        energy_target_kwh: Total energy available (kWh)
        dt: Time step (s)
        
    Returns:
        distance: Total distance travelled (m)
        time: Total time (s)
        log_data: Dictionary of logged data
    """
    
    # Initial State
    v = 0.0
    dist = 0.0
    time = 0.0
    energy_used_kwh = 0.0
    
    log_data = {
        'time': [],
        'distance': [],
        'velocity': [],
        'power_out': [],
        'power_in': [],
        'energy_used': [],
        'rpm': [],
        'gear': []
    }
    
    # Simulation Loop
    launch_rpm = 4000.0 # Launch RPM
    coasting = False
    
    while True:
        v_calc = max(v, 0.1) # Avoid zero division
        
        # Check Energy Status
        if energy_used_kwh >= energy_target_kwh:
            coasting = True
            
        # Gear Selection
        gear = vehicle.select_optimal_gear(v_calc)
        
        # RPMs
        wheel_rpm = vehicle.speed_to_rpm(v_calc, gear)
        engine_rpm = max(wheel_rpm, launch_rpm) # Clutch slip
        
        # Max Engine Capabilities at this RPM
        max_engine_torque = vehicle.power_unit.get_torque(engine_rpm, throttle=1.0)
        max_engine_power = vehicle.power_unit.getPower(engine_rpm, throttle=1.0)
        
        # Max Wheel Torque available (Physical limit of powertrain)
        # T_wheel = T_engine * gear * final * eff
        total_ratio = gear * vehicle.params.final_drive_ratio
        max_wheel_torque = max_engine_torque * total_ratio * vehicle.params.transmission_efficiency
        
        if not coasting:
            # Power Limit Logic
            # We want to limit the Power Output of the vehicle (at wheels? or engine?)
            # Let's assume Power Limit applies to the Engine Power Output (to save fuel)
            # Target Engine Power = min(Max Engine Power, Power Limit)
            
            target_engine_power = min(max_engine_power, power_limit_kw)
            
            # Calculate required Engine Torque for this target power
            # P = T * w
            engine_omega = engine_rpm * 2 * np.pi / 60.0
            target_engine_torque = (target_engine_power * 1000.0) / engine_omega
            
            # Actual Engine Torque (cannot exceed max)
            actual_engine_torque = min(target_engine_torque, max_engine_torque)
            
            # Calculate Throttle
            if max_engine_torque > 0:
                throttle = actual_engine_torque / max_engine_torque
            else:
                throttle = 0.0
                
            # Calculate Wheel Torque
            wheel_torque = actual_engine_torque * total_ratio * vehicle.params.transmission_efficiency
            
            # Calculate Power Input (Fuel Consumption)
            efficiency_pct = vehicle.power_unit.getEfficiency(engine_rpm, throttle)
            
            # Fallback if efficiency is not defined or zero (WE USE THIS AS THIS IS CURRENTLY NOT DEFINED)
            if efficiency_pct <= 1.0: 
                efficiency_pct = 30.0 # Assume 30% efficiency for ICE
                
            # Power Out (Mechanical from Engine)
            engine_power_out_kw = (actual_engine_torque * engine_omega) / 1000.0
            
            # Power In (Fuel)
            power_in_kw = engine_power_out_kw / (efficiency_pct / 100.0)
            
            # Update Energy Used
            energy_step_kwh = power_in_kw * (dt / 3600.0)
            energy_used_kwh += energy_step_kwh
            
        else:
            # Coasting
            target_engine_power = 0.0
            actual_engine_torque = 0.0
            wheel_torque = 0.0
            throttle = 0.0
            engine_power_out_kw = 0.0
            power_in_kw = 0.0
            
        # Calculate Forces
        f_tractive = wheel_torque / vehicle.params.wheel_radius
        
        # Traction Limit (Simplified RWD)
        # We can use the vehicle's compute_longitudinal_force logic but we need to inject our limited torque/power
        # Instead, let's just clamp F_tractive with a simple friction limit for this MVP
        # F_max = weight_rear * mu
        # cog_longitudinal_pos is FRONT mass fraction, so rear fraction = 1 - cog_longitudinal_pos
        weight_rear = vehicle.params.mass * 9.81 * (1.0 - vehicle.params.cog_longitudinal_pos)
        # Add aero load
        f_downforce = vehicle.compute_downforce(v_calc)
        f_aero_rear = f_downforce * (vehicle.params.aero_centre_of_pressure / vehicle.params.wheelbase)
        normal_load_rear = weight_rear + f_aero_rear
        
        # Simple peak mu (e.g. 1.5)
        peak_mu = 1.5 
        f_traction_limit = normal_load_rear * peak_mu
        
        f_tractive = min(f_tractive, f_traction_limit)
        
        # Drag
        f_drag = vehicle.compute_aero_drag(v_calc)
        
        # Rolling Resistance (Simple constant Cr)
        c_rr = 0.015
        f_rolling = vehicle.params.mass * 9.81 * c_rr
        
        # Net Force (THIS IS THE KEY PART!!!)
        f_net = f_tractive - f_drag - f_rolling
        
        # Acceleration
        accel = f_net / vehicle.params.mass
        
        # Update State
        v_new = v + accel * dt
        
        # Check for max speed (drag limited)
        if v_new < v and v_new > v_calc:
             # We are decelerating but still positive speed?
             pass
        
        v = v_new
        dist += v * dt
        time += dt
        
        # Logging
        log_data['time'].append(time)
        log_data['distance'].append(dist)
        log_data['velocity'].append(v)
        log_data['power_out'].append(engine_power_out_kw)
        log_data['power_in'].append(power_in_kw)
        log_data['energy_used'].append(energy_used_kwh)
        log_data['rpm'].append(engine_rpm)
        log_data['gear'].append(gear)
        
        # Stop if velocity drops to 0 (shouldn't happen with positive power)
        if v < 0: break
        
        # Safety break for infinite loops (e.g. if power is too low to move)
        if time > 3600: break 

    return dist, time, log_data

def main():
    # Load Config
    config_path = os.path.join(REPO_ROOT, "config.json")
    if not os.path.exists(config_path):
        # Fallback for different CWD
        config_path = 'config.json'
        
    with open(config_path, 'r') as f:
        config = json.load(f)
        
    # Create Vehicle
    vehicle = create_vehicle(config)
    logger.info(f"Vehicle loaded: {vehicle.params.name}")
    
    # Simulation Parameters
    energy_target_kwh = 0.5 # Example: 0.5 kWh battery/fuel equivalent
    power_limits = [10, 20, 30, 40, 50] # kW
    
    results = []
    
    logger.info(f"Starting Range Test Sweep with Energy Capacity: {energy_target_kwh} kWh")
    
    for p_lim in power_limits:
        logger.info(f"Testing Power Limit: {p_lim} kW")
        dist, time, log = run_range_test(vehicle, p_lim, energy_target_kwh)
        results.append({
            'power_limit': p_lim,
            'distance': dist,
            'time': time,
            'log': log
        })
        logger.info(f"  -> Distance: {dist:.2f} m, Time: {time:.2f} s")
        
    # Visualization
    fig, axs = plt.subplots(2, 2, figsize=(14, 10))
    
    # 1. Distance vs Power Limit
    dists = [r['distance'] for r in results]
    axs[0, 0].plot(power_limits, dists, 'o-', color='blue')
    axs[0, 0].set_xlabel('Power Limit (kW)')
    axs[0, 0].set_ylabel('Total Distance (m)')
    axs[0, 0].set_title(f'Range vs Power Limit (Energy: {energy_target_kwh} kWh)')
    axs[0, 0].grid(True)
    
    # 2. Velocity Profiles
    for r in results:
        axs[0, 1].plot(r['log']['distance'], np.array(r['log']['velocity']) * 3.6, label=f"{r['power_limit']} kW")
    axs[0, 1].set_xlabel('Distance (m)')
    axs[0, 1].set_ylabel('Velocity (kph)')
    axs[0, 1].set_title('Velocity Profile')
    axs[0, 1].legend()
    axs[0, 1].grid(True)
    
    # 3. Power Input vs Time (Efficiency check)
    for r in results:
        axs[1, 0].plot(r['log']['time'], r['log']['power_in'], label=f"{r['power_limit']} kW")
    axs[1, 0].set_xlabel('Time (s)')
    axs[1, 0].set_ylabel('Power Input (kW)')
    axs[1, 0].set_title('Power Consumption vs Time')
    axs[1, 0].legend()
    axs[1, 0].grid(True)

    # 4. Energy Depletion
    for r in results:
        axs[1, 1].plot(r['log']['distance'], r['log']['energy_used'], label=f"{r['power_limit']} kW")
    axs[1, 1].set_xlabel('Distance (m)')
    axs[1, 1].set_ylabel('Energy Used (kWh)')
    axs[1, 1].set_title('Energy Consumption vs Distance')
    axs[1, 1].legend()
    axs[1, 1].grid(True)
    
    plt.tight_layout()
    plt.show()

if __name__ == "__main__":
    main()
