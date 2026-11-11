import logging
import numpy as np
from dataclasses import dataclass
import pandas as pd
from scipy.interpolate import interp1d

logger = logging.getLogger(__name__)

@dataclass
class vehicle_parameters:
    """Core vehicle parameters for point mass simulation."""
    name: str
    mass: float  # kg
    base_mu: float  # dimensionless (base coefficient of friction for tyres)
    frontal_area: float  # m²
    drag_coefficient: float  # dimensionless
    downforce_coefficient: float  # DEPRECATED. Kept for backward compatibility. Use CLA_m2.
    CLA_m2: float  # Downforce coefficient times reference area in m² (Cl * A). F_downforce = 0.5 * rho * v^2 * CLA_m2.
    aero_centre_of_pressure: float  # m from front axle
    wheelbase: float  # m
    front_track_width: float  # m
    rear_track_width: float  # m
    cog_z: float  # m
    max_cog_z: float  # m
    max_roll_angle_deg: float  # degrees
    cog_longitudinal_pos: float  # Fraction of total mass carried by the front axle in static conditions, dimensionless, 0 to 1.
                                  # Equivalently: distance from rear axle to CoG divided by wheelbase (l_r / L).
                                  # Example: 0.516 means 51.6% of static weight on the front axle.
    wheel_radius: float  # m (effective rolling radius)
    final_drive_ratio: float  # dimensionless (final drive gear ratio)
    gear_ratios: list  # dimensionless (gear ratios for each gear)
    transmission_efficiency: float  # dimensionless (0-1, mechanical efficiency)
    roll_stiffness: float  # Nm/rad
    suspension_stiffness: float  # N/m
    damping_coefficient: float  # Ns/m


class PowerUnit:
    """
    Power unit model with torque/power curves and efficiency maps.
    Handles both ICE and electric powertrains.
    """
    
    def __init__(self, power_data: pd.DataFrame):
        """
        Initialize power unit.
        
        Args:
            power_data: DataFrame with columns ['Motor Speed [RPM]', 'Continuous Power [kW]', 'Peak Power [kW]']
        """
        self.power_data = self.setup_from_data(power_data)
        if self.power_data is None:
            raise ValueError("power_data must be a pandas DataFrame and cannot be None.")

    def setup_from_data(self, df: pd.DataFrame):
        """Setup power unit from DataFrame."""
        return df
    
class tyre_model:
    """
    tyre model for grip calculations.
    Use interpolated lookup tables for tyre forces.
    """
    
    def __init__(self, tyre_data_lat: pd.DataFrame, tyre_data_long: pd.DataFrame):
        """
        Initialize tyre model.
        
        Args:
            tyre_data_lat: DataFrame with lateral tyre data (e.g. slip angle vs lateral force)
            tyre_data_long: DataFrame with longitudinal tyre data (e.g. slip ratio vs longitudinal force)
        """
        self.tyre_data_lat = tyre_data_lat
        self.tyre_data_long = tyre_data_long
        self.lat_force_interp = interp1d(
            tyre_data_lat['Slip Angle [deg]'],
            tyre_data_lat['Lateral Force [N]'],
            kind='linear',
            fill_value='extrapolate'
        )
        self.tyre_data = self.setup_from_data(tyre_data_lat, tyre_data_long)
        if self.tyre_data is None:
            raise ValueError("tyre_data must be a pandas DataFrame and cannot be None.")
        
    def setup_from_data(self, df_lat: pd.DataFrame, df_long: pd.DataFrame):
        """Setup tyre model from DataFrames."""
        return {
            'lat_tyre_data': df_lat,
            'long_tyre_data': df_long
        }

    def get_lateral_force(self, slip_angle: float, normal_load: float = None) -> float:
        """
        Get lateral force for a given slip angle.
        For MVP, we ignore normal_load (use constant from dummy data).
        
        Args:
            slip_angle: Slip angle in degrees
        Returns:
            Lateral force in N
        """
        return float(self.lat_force_interp(slip_angle))
    
class Vehicle:
    """Complete vehicle model combining all subsystems."""
    
    def __init__(self, parameters: vehicle_parameters, 
                 power_unit: PowerUnit, 
                 tyre_model: tyre_model,
                 config):
        """
        Initialize complete vehicle model.
        
        Args:
            parameters: Vehicle physical parameters
            power_unit: Power unit model
            tyre_model: Tyre model
            config: Configuration dictionary
        """
        self.params = parameters
        self.power_unit = power_unit
        self.tyre_model = tyre_model
        self.config = config
        self.base_mu_reference = max(float(parameters.base_mu), 1e-6)
        scenario_cfg = config.get('scenario', {}) if isinstance(config, dict) else {}
        try:
            self.scenario_name = str(scenario_cfg.get('name', 'baseline')).strip() or 'baseline'
        except Exception:
            self.scenario_name = 'baseline'
        try:
            self.scenario_grip_scale = float(scenario_cfg.get('grip_scale', 1.0))
        except (TypeError, ValueError):
            self.scenario_grip_scale = 1.0
        try:
            self.scenario_air_density_scale = float(scenario_cfg.get('air_density_scale', 1.0))
        except (TypeError, ValueError):
            self.scenario_air_density_scale = 1.0
        self.scenario_grip_scale = max(self.scenario_grip_scale, 0.0)
        self.scenario_air_density_scale = max(self.scenario_air_density_scale, 0.0)
        
        # Calculate derived parameters
        self.weight = parameters.mass * 9.81  # N
        
    def compute_static_normal_load(self) -> float:
        """
        Compute static normal load per tire (assuming equal distribution).
        For point mass model without load transfer.
        
        Returns:
            Normal load per tire in N
        """
        return self.params.mass * 9.81 / 4.0
        
    def compute_tyre_forces(self, slip_angle_front: float, slip_angle_rear: float,
                            normal_load_front: float = None, normal_load_rear: float = None):
        """
        Compute lateral tire forces using the tire model.
        Args:
            slip_angle_front: Front tire slip angle in degrees
            slip_angle_rear: Rear tire slip angle in degrees
            normal_load_front: Optional front tyre normal load per tyre in N
            normal_load_rear: Optional rear tyre normal load per tyre in N
        Returns:
            (f_front, f_rear): Lateral forces in N
        """
        if normal_load_front is None:
            normal_load_front = self.compute_static_normal_load()
        if normal_load_rear is None:
            normal_load_rear = self.compute_static_normal_load()
        # The tyre model already applies base_mu internally (D = peak * base_mu).
        # Only scenario_grip_scale is applied here as a separate surface condition multiplier.
        # Multiplying by base_mu/base_mu_reference again would double-count the base friction.
        f_front = self.tyre_model.get_lateral_force(slip_angle_front, normal_load=normal_load_front) * 2 * self.scenario_grip_scale
        f_rear = self.tyre_model.get_lateral_force(slip_angle_rear, normal_load=normal_load_rear) * 2 * self.scenario_grip_scale
        return f_front, f_rear
    
    def compute_yaw_moment(self, f_front: float, f_rear: float, steer_angle: float) -> float:
        """
        Compute yaw moment based on tire forces and steering angle.
        
        For steady-state cornering, yaw moment = 0 when:
        f_front * l_f = f_rear * l_r
        
        Args:
            f_front: Front lateral force in N
            f_rear: Rear lateral force in N
            steer_angle: Steering angle in degrees
        
        Returns:
            Yaw moment in Nm
        """
        # cog_longitudinal_pos = front mass fraction = l_r / L.
        # l_r: distance from CoG to rear axle. l_f: distance from CoG to front axle.
        l_r = self.params.wheelbase * self.params.cog_longitudinal_pos         # CoG to rear axle (m)
        l_f = self.params.wheelbase * (1 - self.params.cog_longitudinal_pos)   # CoG to front axle (m)
        # Yaw moment = (front force × front moment arm) - (rear force × rear moment arm)
        # In steady state, this should equal zero
        m_z = f_front * l_f - f_rear * l_r
        return m_z
    
    def compute_lateral_acceleration(self, f_front: float, f_rear: float, v_car: float) -> float:
        """
        Compute lateral acceleration based on tire forces and vehicle speed.
        Args:
            f_front: Front lateral force in N
            f_rear: Rear lateral force in N
            v_car: Vehicle speed in m/s
        Returns:
            Lateral acceleration in m/s^2
        """
        a_y = (f_front + f_rear) / self.params.mass
        return a_y
    
    def compute_aero_drag(self, v_car: float) -> float:
        """
        Compute aerodynamic drag force at given speed.
        
        F_drag = 0.5 * rho * Cd * A * v^2
        
        Args:
            v_car: Vehicle speed in m/s
            
        Returns:
            Drag force in N
        """
        # Use air density from config if available, else default to 1.225
        rho = self.config.get('ambient_conditions', {}).get('air_density', 1.225)
        rho = float(rho) * self.scenario_air_density_scale
        f_drag = 0.5 * rho * self.params.drag_coefficient * self.params.frontal_area * v_car**2
        return f_drag
    
    def compute_downforce(self, v_car: float) -> float:
        """
        Compute aerodynamic downforce at given speed.

        F_downforce = 0.5 * rho * CLA_m2 * v^2

        CLA_m2 is the downforce coefficient times reference area (Cl * A) in m².
        Using CLA_m2 directly avoids the misleading intermediate step of multiplying
        a dimensionless Cl by a separate frontal_area — the product is what matters physically.

        Args:
            v_car: Vehicle speed in m/s

        Returns:
            Downforce in N
        """
        # Use air density from config if available, else default to 1.225
        rho = self.config.get('ambient_conditions', {}).get('air_density', 1.225)
        rho = float(rho) * self.scenario_air_density_scale
        f_downforce = 0.5 * rho * self.params.CLA_m2 * v_car**2
        return f_downforce
    
    def speed_to_rpm(self, v_car: float, gear_ratio: float) -> float:
        """
        Convert vehicle speed to engine RPM for given gear ratio.
        
        RPM = (v * 60 * gearRatio * finalDrive) / (2 * pi * wheel_radius)
        
        Args:
            v_car: Vehicle speed in m/s
            gear_ratio: Gear ratio (dimensionless)
            
        Returns:
            Engine RPM
        """
        if v_car < 0.01:  # Avoid division issues at very low speeds
            return 0.0
        
        # RPM = (speed * 60 * total_gear_ratio) / (2 * pi * wheel_radius)
        total_gear_ratio = gear_ratio * self.params.final_drive_ratio
        rpm = (v_car * 60 * total_gear_ratio) / (2 * np.pi * self.params.wheel_radius)
        return rpm
    
    def compute_wheel_torque(self, rpm: float, gear_ratio: float, throttle: float = 1.0) -> float:
        """
        Compute wheel torque from engine RPM and gear ratio.
        
        T_wheel = T_engine * gear_ratio * final_drive * efficiency
        
        Args:
            rpm: Engine RPM
            gear_ratio: Gear ratio (dimensionless)
            throttle: Throttle position (0 to 1)
            
        Returns:
            Wheel torque in Nm
        """
        # Get engine torque from powertrain
        engine_torque = self.power_unit.get_torque(rpm, throttle)
        # Apply gear ratios and transmission efficiency
        total_gear_ratio = gear_ratio * self.params.final_drive_ratio
        wheel_torque = engine_torque * total_gear_ratio * self.params.transmission_efficiency
        return wheel_torque
    
    def compute_longitudinal_force(self, v_car: float, gear_ratio: float, throttle: float = 1.0) -> float:
        """
        Compute longitudinal force at wheels for given speed and gear.
        
        F_x = T_wheel / wheel_radius - F_drag
        
        Args:
            v_car: Vehicle speed in m/s
            gear_ratio: Gear ratio (dimensionless)
            throttle: Throttle position (0 to 1)
            
        Returns:
            Net longitudinal force in N
        """
        # Convert speed to RPM
        rpm = self.speed_to_rpm(v_car, gear_ratio)
        # Get wheel torque
        wheel_torque = self.compute_wheel_torque(rpm, gear_ratio, throttle)
        # Convert torque to force at wheel contact patch
        f_traction = wheel_torque / self.params.wheel_radius
        # Subtract drag force
        f_drag = self.compute_aero_drag(v_car)
        # Net longitudinal force
        f_x = f_traction - f_drag
        return f_x
    
    def select_optimal_gear(self, v_car: float) -> float:
        """
        Select the optimal gear for maximum acceleration at given speed.
        
        Args:
            v_car: Vehicle speed in m/s
            
        Returns:
            Optimal gear ratio
        """
        max_force = -float('inf')
        optimal_gear = self.params.gear_ratios[0]
        
        # Try each gear and find which gives maximum force
        for gear_ratio in self.params.gear_ratios:
            f_x = self.compute_longitudinal_force(v_car, gear_ratio)
            if f_x > max_force:
                max_force = f_x
                optimal_gear = gear_ratio
        return optimal_gear
        
from vehicle.Tyres.baseTyre import create_tyre_model
from .Powertrain.basePowertrain import create_powertrain_model
import json
import os


def params_from_dict(data: dict) -> vehicle_parameters:
    """
    Create vehicle_parameters from a nested parameter dictionary.

    Args:
        data: Dictionary with nested structure (general, aerodynamics, geometry, etc)

    Returns:
        vehicle_parameters object
    """
    aero = data['aerodynamics']
    frontal_area = float(aero['frontal_area'])
    downforce_coefficient = float(aero['downforce_coefficient'])

    # CLA_m2 is downforce coefficient times reference area in m².
    # Use it directly when present. Otherwise derive from legacy fields and warn once.
    if 'CLA_m2' in aero:
        CLA_m2 = float(aero['CLA_m2'])
    else:
        CLA_m2 = downforce_coefficient * frontal_area
        logger.warning(
            "parameters.json is missing 'CLA_m2'. Computed from downforce_coefficient * frontal_area "
            f"= {downforce_coefficient} * {frontal_area} = {CLA_m2:.6f} m². "
            "Add 'CLA_m2' to parameters.json to suppress this warning."
        )

    return vehicle_parameters(
        name=data['general']['name'],
        mass=data['general']['mass'],
        base_mu=data['general']['base_mu'],
        frontal_area=frontal_area,
        drag_coefficient=aero['drag_coefficient'],
        downforce_coefficient=downforce_coefficient,
        CLA_m2=CLA_m2,
        aero_centre_of_pressure=aero['aero_cp'],
        wheelbase=data['geometry']['wheelbase'],
        front_track_width=data['geometry']['front_track_width'],
        rear_track_width=data['geometry']['rear_track_width'],
        cog_z=data['geometry']['cog_z'],
        cog_longitudinal_pos=data['geometry']['cog_longitudinal_pos'],
        max_cog_z=data['geometry']['max_cog_z'],
        wheel_radius=data['drivetrain']['wheel_radius'],
        final_drive_ratio=data['drivetrain']['final_drive_ratio'],
        gear_ratios=data['drivetrain']['gear_ratios'],
        transmission_efficiency=data['drivetrain']['transmission_efficiency'],
        roll_stiffness=data['vehicle_dynamics']['roll_stiffness'],
        suspension_stiffness=data['vehicle_dynamics']['suspension_stiffness'],
        damping_coefficient=data['vehicle_dynamics']['damping_coefficient'],
        max_roll_angle_deg=data['vehicle_dynamics']['max_roll_angle_deg'],
    )


def load_vehicle_parameters(file_path: str) -> vehicle_parameters:
    """
    Load vehicle parameters from a JSON configuration file.
    Args:
        file_path: Path to the parameters JSON file
    Returns:
        vehicle_parameters object
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Vehicle parameters file not found: {file_path}")
    with open(file_path, 'r') as f:
        data = json.load(f)
    params = params_from_dict(data)
    logger.info(f"Loaded vehicle parameters from {file_path}")
    return params

def create_vehicle(config) -> Vehicle:
    """Create vehicle from configuration file."""
    vp = config.get('vehicle_parameters', 'parameters.json')
    if isinstance(vp, dict):
        params = params_from_dict(vp)
    else:
        params = load_vehicle_parameters(vp)
    power_unit = create_powertrain_model(config.get('powertrain', {}))
    tyre_config = dict(config.get('tyre_model', {}))
    tyre_config.setdefault('base_mu', params.base_mu)
    model_variant = str(config.get('ab_testing', {}).get('model_variant', config.get('model_variant', 'baseline'))).strip().lower()
    tyre_config.setdefault('model_variant', model_variant)
    tyre_model = create_tyre_model(tyre_config)
    loaded_vehicle = Vehicle(params, power_unit, tyre_model, config)
    return loaded_vehicle
