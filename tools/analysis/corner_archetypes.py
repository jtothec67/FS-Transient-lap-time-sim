"""
Corner Archetypes Testing Script
================================
Tests vehicle performance across 8 synthetic track corner archetypes
representing realistic Formula Student corner types with variable radius profiles.

Corner Types:
1. Hairpin - Tight U-turn (9m outside diameter minimum per FS rules)
2. 90-degree corner - Standard right-angle turn
3. Medium-speed sweeper - Longer radius constant turn
4. High-speed corner - Fast, gentle curve
5. Decreasing-radius corner - Entry fast, exit tight
6. Increasing-radius corner - Entry tight, exit fast
7. Chicane - S-bend left-right combination
8. Linked double-apex corner - Two apexes with brief straight

Formula Student Track Rules Reference:
- Straights: No longer than 80m
- Constant Turns: up to 50m diameter (25m radius)
- Hairpin Turns: Minimum 9m outside diameter
- Minimum track width: 3m

Outputs:
- Per-corner plots: lat/long accel, speed, radius, curvature, X-Y track
- Overlay comparison plots across all corners
- Summary table with key metrics
"""

import sys
import os
import json
import logging
from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Callable
from enum import Enum
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))

# Add src directory to path for imports
sys.path.insert(0, os.path.join(REPO_ROOT, "src"))

from track.track import Track, TrackPoint
from vehicle.vehicle import create_vehicle
from simulator.util.calcSpeedProfile import (
    optimise_speed_at_points,
    forward_pass,
    backward_pass
)

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# =============================================================================
# ENUMS AND DATA CLASSES
# =============================================================================

class RadiusProfile(Enum):
    """Radius profile types for corners."""
    CONSTANT = "constant"
    INCREASING = "increasing"  # Tight entry, opens up
    DECREASING = "decreasing"  # Open entry, tightens


class CornerType(Enum):
    """Corner archetype types."""
    HAIRPIN = "Hairpin"
    NINETY_DEGREE = "90-Degree"
    MEDIUM_SWEEPER = "Medium Sweeper"
    HIGH_SPEED = "High-Speed"
    DECREASING_RADIUS = "Decreasing Radius"
    INCREASING_RADIUS = "Increasing Radius"
    CHICANE = "Chicane"
    DOUBLE_APEX = "Double Apex"


@dataclass
class CornerParameters:
    """
    Parameters defining a corner archetype.
    
    All units in SI (meters, radians, m/s).
    """
    name: str
    corner_type: CornerType
    turn_angle: float  # Total turn angle in radians (positive = left, use abs for direction)
    min_radius: float  # Minimum radius in meters
    max_radius: float  # Maximum radius (for variable profiles)
    radius_profile: RadiusProfile
    entry_straight: float = 20.0  # Straight before corner (m)
    exit_straight: float = 20.0  # Straight after corner (m)
    num_points: int = 200  # Discretization resolution
    
    # For chicanes and double-apex
    secondary_angle: Optional[float] = None  # Second turn angle
    secondary_radius: Optional[float] = None  # Second turn radius
    mid_straight: Optional[float] = None  # Straight between turns
    
    # Direction: 1 = left turn, -1 = right turn
    direction: int = 1
    
    def __post_init__(self):
        """Validate parameters."""
        if self.min_radius <= 0:
            raise ValueError("min_radius must be positive")
        if self.max_radius < self.min_radius:
            self.max_radius = self.min_radius


@dataclass
class CornerGeometry:
    """
    Generated corner geometry data.
    """
    x: np.ndarray
    y: np.ndarray
    z: np.ndarray
    distances: np.ndarray
    curvatures: np.ndarray
    radii: np.ndarray
    headings: np.ndarray
    total_length: float


@dataclass
class SimulationResults:
    """
    Results from running a corner through the simulator.
    """
    params: CornerParameters
    geometry: CornerGeometry
    track: Track
    final_speeds: np.ndarray
    corner_speeds: np.ndarray
    g_lat: np.ndarray
    g_long: np.ndarray
    
    # Computed metrics
    min_speed_kph: float = 0.0
    max_speed_kph: float = 0.0
    avg_speed_kph: float = 0.0
    peak_g_lat: float = 0.0
    peak_g_long_accel: float = 0.0
    peak_g_long_decel: float = 0.0
    corner_time: float = 0.0


# =============================================================================
# GEOMETRY GENERATION
# =============================================================================

def generate_straight_segment(
    start_x: float,
    start_y: float,
    heading: float,
    length: float,
    num_points: int
) -> Tuple[np.ndarray, np.ndarray]:
    """Generate a straight segment."""
    t = np.linspace(0, length, num_points)
    x = start_x + t * np.cos(heading)
    y = start_y + t * np.sin(heading)
    return x, y


def generate_arc_segment(
    start_x: float,
    start_y: float,
    start_heading: float,
    angle: float,
    radius_func: Callable[[float], float],
    num_points: int,
    direction: int = 1
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    Generate an arc segment with variable radius.
    
    Args:
        start_x, start_y: Starting position
        start_heading: Initial heading (radians)
        angle: Total turn angle (radians, positive)
        radius_func: Function that returns radius given progress [0, 1]
        num_points: Number of points to generate
        direction: 1 for left turn, -1 for right turn
    
    Returns:
        x, y coordinates, curvatures, and radii arrays
    """
    # Parameter along the arc
    t = np.linspace(0, 1, num_points)
    
    # Get radius at each point
    radii = np.array([radius_func(ti) for ti in t])
    curvatures = direction / radii
    
    # Integrate heading change
    # dθ/ds = κ, and we parameterize by t where s = ∫ radius * dθ
    x = np.zeros(num_points)
    y = np.zeros(num_points)
    headings = np.zeros(num_points)
    
    x[0] = start_x
    y[0] = start_y
    headings[0] = start_heading
    
    # Integrate position using trapezoidal rule
    angle_step = angle / (num_points - 1)
    
    for i in range(1, num_points):
        # Progress through the turn
        headings[i] = headings[i-1] + direction * angle_step
        
        # Average radius for this segment
        r_avg = (radii[i] + radii[i-1]) / 2
        ds = r_avg * angle_step
        
        # Move along the path
        avg_heading = (headings[i] + headings[i-1]) / 2
        x[i] = x[i-1] + ds * np.cos(avg_heading)
        y[i] = y[i-1] + ds * np.sin(avg_heading)
    
    return x, y, curvatures, radii


def create_radius_function(
    profile: RadiusProfile,
    min_radius: float,
    max_radius: float
) -> Callable[[float], float]:
    """
    Create a radius function based on profile type.
    
    Args:
        profile: Type of radius profile
        min_radius: Minimum radius
        max_radius: Maximum radius
    
    Returns:
        Function that takes progress [0, 1] and returns radius
    """
    if profile == RadiusProfile.CONSTANT:
        return lambda t: min_radius
    elif profile == RadiusProfile.INCREASING:
        # Starts at min_radius, ends at max_radius
        return lambda t: min_radius + t * (max_radius - min_radius)
    elif profile == RadiusProfile.DECREASING:
        # Starts at max_radius, ends at min_radius
        return lambda t: max_radius - t * (max_radius - min_radius)
    else:
        return lambda t: min_radius


def generate_corner_geometry(params: CornerParameters) -> CornerGeometry:
    """
    Generate complete corner geometry from parameters.
    
    Args:
        params: Corner parameters
    
    Returns:
        CornerGeometry object with all geometric data
    """
    all_x = []
    all_y = []
    
    # Points allocation
    n_entry = max(20, params.num_points // 5)
    n_corner = params.num_points - 2 * (params.num_points // 5)
    n_exit = max(20, params.num_points // 5)
    
    # Start position and heading
    current_x, current_y = 0.0, 0.0
    current_heading = 0.0  # Start heading east
    
    # 1. Entry straight
    if params.entry_straight > 0:
        x_entry, y_entry = generate_straight_segment(
            current_x, current_y, current_heading,
            params.entry_straight, n_entry
        )
        all_x.extend(x_entry[:-1])  # Exclude last point to avoid duplicates
        all_y.extend(y_entry[:-1])
        current_x, current_y = x_entry[-1], y_entry[-1]
    
    # 2. Main corner (or first part for chicane/double-apex)
    if params.corner_type == CornerType.CHICANE:
        # First turn
        radius_func1 = create_radius_function(
            RadiusProfile.CONSTANT, params.min_radius, params.min_radius
        )
        x_c1, y_c1, curv1, rad1 = generate_arc_segment(
            current_x, current_y, current_heading,
            abs(params.turn_angle), radius_func1,
            n_corner // 3, params.direction
        )
        all_x.extend(x_c1[:-1])
        all_y.extend(y_c1[:-1])
        current_x, current_y = x_c1[-1], y_c1[-1]
        current_heading += params.direction * abs(params.turn_angle)
        
        # Mid straight (short)
        mid_length = params.mid_straight or 5.0
        x_mid, y_mid = generate_straight_segment(
            current_x, current_y, current_heading,
            mid_length, n_corner // 6
        )
        all_x.extend(x_mid[:-1])
        all_y.extend(y_mid[:-1])
        current_x, current_y = x_mid[-1], y_mid[-1]
        
        # Second turn (opposite direction)
        sec_radius = params.secondary_radius or params.min_radius
        radius_func2 = create_radius_function(
            RadiusProfile.CONSTANT, sec_radius, sec_radius
        )
        sec_angle = params.secondary_angle or params.turn_angle
        x_c2, y_c2, curv2, rad2 = generate_arc_segment(
            current_x, current_y, current_heading,
            abs(sec_angle), radius_func2,
            n_corner // 3, -params.direction  # Opposite direction
        )
        all_x.extend(x_c2[:-1])
        all_y.extend(y_c2[:-1])
        current_x, current_y = x_c2[-1], y_c2[-1]
        current_heading += -params.direction * abs(sec_angle)
        
    elif params.corner_type == CornerType.DOUBLE_APEX:
        # First apex
        radius_func1 = create_radius_function(
            RadiusProfile.CONSTANT, params.min_radius, params.min_radius
        )
        half_angle = abs(params.turn_angle) / 2
        x_c1, y_c1, curv1, rad1 = generate_arc_segment(
            current_x, current_y, current_heading,
            half_angle * 0.8, radius_func1,
            n_corner // 3, params.direction
        )
        all_x.extend(x_c1[:-1])
        all_y.extend(y_c1[:-1])
        current_x, current_y = x_c1[-1], y_c1[-1]
        current_heading += params.direction * half_angle * 0.8
        
        # Brief straighter section (larger radius)
        mid_length = params.mid_straight or 8.0
        larger_radius = params.max_radius * 2
        radius_func_mid = create_radius_function(
            RadiusProfile.CONSTANT, larger_radius, larger_radius
        )
        x_mid, y_mid, curv_mid, rad_mid = generate_arc_segment(
            current_x, current_y, current_heading,
            half_angle * 0.4, radius_func_mid,
            n_corner // 6, params.direction
        )
        all_x.extend(x_mid[:-1])
        all_y.extend(y_mid[:-1])
        current_x, current_y = x_mid[-1], y_mid[-1]
        current_heading += params.direction * half_angle * 0.4
        
        # Second apex
        sec_radius = params.secondary_radius or params.min_radius
        radius_func2 = create_radius_function(
            RadiusProfile.CONSTANT, sec_radius, sec_radius
        )
        x_c2, y_c2, curv2, rad2 = generate_arc_segment(
            current_x, current_y, current_heading,
            half_angle * 0.8, radius_func2,
            n_corner // 3, params.direction
        )
        all_x.extend(x_c2[:-1])
        all_y.extend(y_c2[:-1])
        current_x, current_y = x_c2[-1], y_c2[-1]
        current_heading += params.direction * half_angle * 0.8
        
    else:
        # Standard single corner with variable radius
        radius_func = create_radius_function(
            params.radius_profile, params.min_radius, params.max_radius
        )
        x_corner, y_corner, curvatures, radii = generate_arc_segment(
            current_x, current_y, current_heading,
            abs(params.turn_angle), radius_func,
            n_corner, params.direction
        )
        all_x.extend(x_corner[:-1])
        all_y.extend(y_corner[:-1])
        current_x, current_y = x_corner[-1], y_corner[-1]
        current_heading += params.direction * abs(params.turn_angle)
    
    # 3. Exit straight
    if params.exit_straight > 0:
        x_exit, y_exit = generate_straight_segment(
            current_x, current_y, current_heading,
            params.exit_straight, n_exit
        )
        all_x.extend(x_exit)
        all_y.extend(y_exit)
    
    # Convert to arrays
    x = np.array(all_x)
    y = np.array(all_y)
    z = np.zeros_like(x)  # Flat track
    
    # Compute distances
    dx = np.diff(x)
    dy = np.diff(y)
    segment_lengths = np.sqrt(dx**2 + dy**2)
    distances = np.zeros(len(x))
    distances[1:] = np.cumsum(segment_lengths)
    
    # Compute curvatures using finite differences
    curvatures = compute_curvatures(x, y, distances)
    
    # Compute radii (inverse of curvature, handle zeros)
    radii = np.zeros_like(curvatures)
    nonzero_mask = np.abs(curvatures) > 1e-6
    radii[nonzero_mask] = 1.0 / np.abs(curvatures[nonzero_mask])
    radii[~nonzero_mask] = np.inf  # Straight sections
    
    # Compute headings
    headings = compute_headings(x, y)
    
    return CornerGeometry(
        x=x,
        y=y,
        z=z,
        distances=distances,
        curvatures=curvatures,
        radii=radii,
        headings=headings,
        total_length=distances[-1]
    )


def compute_curvatures(x: np.ndarray, y: np.ndarray, distances: np.ndarray) -> np.ndarray:
    """
    Compute curvature at each point using finite differences.
    κ = (x'y'' - y'x'') / (x'^2 + y'^2)^(3/2)
    """
    n = len(x)
    curvatures = np.zeros(n)
    
    for i in range(1, n-1):
        ds_back = distances[i] - distances[i-1]
        ds_forward = distances[i+1] - distances[i]
        
        if ds_back > 1e-10 and ds_forward > 1e-10:
            # First derivatives
            dx_ds = (x[i+1] - x[i-1]) / (distances[i+1] - distances[i-1])
            dy_ds = (y[i+1] - y[i-1]) / (distances[i+1] - distances[i-1])
            
            # Second derivatives
            d2x_ds2 = ((x[i+1] - x[i]) / ds_forward - (x[i] - x[i-1]) / ds_back) / (0.5 * (ds_forward + ds_back))
            d2y_ds2 = ((y[i+1] - y[i]) / ds_forward - (y[i] - y[i-1]) / ds_back) / (0.5 * (ds_forward + ds_back))
            
            numerator = dx_ds * d2y_ds2 - dy_ds * d2x_ds2
            denominator = (dx_ds**2 + dy_ds**2)**(3/2)
            
            if denominator > 1e-10:
                curvatures[i] = numerator / denominator
    
    curvatures[0] = curvatures[1] if n > 1 else 0.0
    curvatures[-1] = curvatures[-2] if n > 1 else 0.0
    
    return curvatures


def compute_headings(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Compute heading angles at each point."""
    n = len(x)
    headings = np.zeros(n)
    
    for i in range(n-1):
        dx = x[i+1] - x[i]
        dy = y[i+1] - y[i]
        headings[i] = np.arctan2(dy, dx)
    
    headings[-1] = headings[-2] if n > 1 else 0.0
    return headings


# =============================================================================
# SIMULATOR ADAPTER
# =============================================================================

def geometry_to_track(geometry: CornerGeometry) -> Track:
    """Convert CornerGeometry to Track object for simulator."""
    points = []
    for i in range(len(geometry.x)):
        point = TrackPoint(
            distance=geometry.distances[i],
            x=geometry.x[i],
            y=geometry.y[i],
            z=geometry.z[i],
            curvature=abs(geometry.curvatures[i]),  # Simulator uses positive curvature
            heading=geometry.headings[i],
            elevation_angle=0.0
        )
        points.append(point)
    
    return Track(points, is_closed=False)


def run_simulation(track: Track, vehicle, config) -> Tuple[np.ndarray, np.ndarray]:
    """
    Run the vehicle simulator on a track.
    
    Args:
        track: Track object
        vehicle: Vehicle object from create_vehicle()
        config: Configuration dict
    
    Returns:
        (final_speeds, corner_speeds) arrays
    """
    # Pass 1: Find corner speed limits
    corner_speeds = optimise_speed_at_points(track.points, vehicle, config)
    
    # Pass 2: Forward pass (acceleration limited)
    forward_speeds = forward_pass(track, vehicle, corner_speeds)
    
    # Pass 3: Backward pass (braking limited)
    backward_speeds = backward_pass(track, vehicle, corner_speeds)
    
    # Final speeds are minimum of forward and backward
    final_speeds = np.minimum(forward_speeds, backward_speeds)
    
    return final_speeds, np.array(corner_speeds)


def calculate_accelerations(
    distances: np.ndarray,
    speeds: np.ndarray,
    curvatures: np.ndarray
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Calculate lateral and longitudinal g-forces.
    
    Returns:
        (g_lat, g_long) arrays
    """
    n = len(distances)
    g_lat = np.zeros(n)
    g_long = np.zeros(n)
    
    for i in range(1, n):
        ds = distances[i] - distances[i-1]
        v_prev = speeds[i-1]
        v_curr = speeds[i]
        
        # Longitudinal g: from speed change
        if ds > 1e-6:
            g_long[i] = ((v_curr**2 - v_prev**2) / (2 * ds)) / 9.81
        
        # Lateral g: centripetal acceleration
        g_lat[i] = v_curr**2 * abs(curvatures[i]) / 9.81
    
    g_lat[0] = g_lat[1] if n > 1 else 0.0
    g_long[0] = g_long[1] if n > 1 else 0.0
    
    return g_lat, g_long


def simulate_corner(
    params: CornerParameters,
    vehicle,
    config
) -> SimulationResults:
    """
    Complete simulation pipeline for a corner.
    
    Args:
        params: Corner parameters
        vehicle: Vehicle object
        config: Configuration dict
    
    Returns:
        SimulationResults object
    """
    logger.info(f"\n{'='*60}")
    logger.info(f"Simulating: {params.name} ({params.corner_type.value})")
    logger.info(f"Min radius: {params.min_radius:.1f}m, Turn angle: {np.degrees(params.turn_angle):.1f}°")
    logger.info(f"{'='*60}")
    
    # Generate geometry
    geometry = generate_corner_geometry(params)
    logger.info(f"Generated geometry: {len(geometry.x)} points, {geometry.total_length:.1f}m total")
    
    # Convert to Track
    track = geometry_to_track(geometry)
    
    # Run simulation
    final_speeds, corner_speeds = run_simulation(track, vehicle, config)
    
    # Calculate accelerations
    g_lat, g_long = calculate_accelerations(
        geometry.distances, final_speeds, geometry.curvatures
    )
    
    # Compute metrics
    final_speeds_kph = final_speeds * 3.6
    
    # Corner time calculation
    corner_time = 0.0
    for i in range(1, len(geometry.distances)):
        ds = geometry.distances[i] - geometry.distances[i-1]
        v_avg = (final_speeds[i] + final_speeds[i-1]) / 2
        if v_avg > 0:
            corner_time += ds / v_avg
    
    results = SimulationResults(
        params=params,
        geometry=geometry,
        track=track,
        final_speeds=final_speeds,
        corner_speeds=corner_speeds,
        g_lat=g_lat,
        g_long=g_long,
        min_speed_kph=float(np.min(final_speeds_kph)),
        max_speed_kph=float(np.max(final_speeds_kph)),
        avg_speed_kph=float(np.mean(final_speeds_kph)),
        peak_g_lat=float(np.max(np.abs(g_lat))),
        peak_g_long_accel=float(np.max(g_long)),
        peak_g_long_decel=float(np.min(g_long)),
        corner_time=corner_time
    )
    
    logger.info(f"Results: Min speed: {results.min_speed_kph:.1f} kph, "
                f"Time: {results.corner_time:.2f}s, Peak g_lat: {results.peak_g_lat:.2f}g")
    
    return results


# =============================================================================
# PLOTTING
# =============================================================================

def plot_corner_results(results: SimulationResults, show: bool = False):
    """
    Generate comprehensive plots for a single corner.
    
    Creates a 2x3 subplot figure with:
    - Lateral acceleration vs distance
    - Longitudinal acceleration vs distance
    - Speed vs distance
    - Radius vs distance
    - Curvature vs distance
    - X-Y track plot
    """
    params = results.params
    geom = results.geometry
    
    sns.set_theme(style="darkgrid", context="notebook")
    
    fig, axes = plt.subplots(2, 3, figsize=(16, 10))
    fig.suptitle(
        f"{params.name} ({params.corner_type.value})\n"
        f"Min R: {params.min_radius:.1f}m | Turn: {np.degrees(params.turn_angle):.0f}° | "
        f"Profile: {params.radius_profile.value}",
        fontsize=14, fontweight='bold'
    )
    
    distances = geom.distances
    speeds_kph = results.final_speeds * 3.6
    corner_speeds_kph = results.corner_speeds * 3.6
    
    # Plot 1: Lateral Acceleration
    ax1 = axes[0, 0]
    ax1.plot(distances, results.g_lat, 'g-', linewidth=2, label='Lateral G')
    ax1.axhline(y=results.peak_g_lat, color='r', linestyle='--', alpha=0.7,
                label=f'Peak: {results.peak_g_lat:.2f}g')
    ax1.set_xlabel('Distance (m)')
    ax1.set_ylabel('Lateral Acceleration (g)')
    ax1.set_title('Lateral Acceleration')
    ax1.legend(loc='upper right')
    ax1.grid(True, alpha=0.3)
    
    # Plot 2: Longitudinal Acceleration
    ax2 = axes[0, 1]
    ax2.plot(distances, results.g_long, 'orange', linewidth=2, label='Long G')
    ax2.axhline(y=0, color='gray', linestyle='-', alpha=0.5)
    ax2.axhline(y=results.peak_g_long_accel, color='g', linestyle='--', alpha=0.7,
                label=f'Peak Accel: {results.peak_g_long_accel:.2f}g')
    ax2.axhline(y=results.peak_g_long_decel, color='r', linestyle='--', alpha=0.7,
                label=f'Peak Decel: {results.peak_g_long_decel:.2f}g')
    ax2.set_xlabel('Distance (m)')
    ax2.set_ylabel('Longitudinal Acceleration (g)')
    ax2.set_title('Longitudinal Acceleration')
    ax2.legend(loc='upper right')
    ax2.grid(True, alpha=0.3)
    
    # Plot 3: Speed
    ax3 = axes[0, 2]
    ax3.plot(distances, speeds_kph, 'b-', linewidth=2, label='Actual Speed')
    ax3.plot(distances, corner_speeds_kph, 'gray', linestyle='--', alpha=0.7,
             label='Corner Limit')
    ax3.axhline(y=results.min_speed_kph, color='r', linestyle=':', alpha=0.7,
                label=f'Min: {results.min_speed_kph:.1f} kph')
    ax3.set_xlabel('Distance (m)')
    ax3.set_ylabel('Speed (kph)')
    ax3.set_title(f'Speed Profile (Time: {results.corner_time:.2f}s)')
    ax3.legend(loc='upper right')
    ax3.grid(True, alpha=0.3)
    
    # Plot 4: Radius
    ax4 = axes[1, 0]
    # Cap radius display at reasonable value for visualization
    radii_display = np.clip(geom.radii, 0, 100)
    ax4.plot(distances, radii_display, 'm-', linewidth=2)
    ax4.axhline(y=params.min_radius, color='r', linestyle='--', alpha=0.7,
                label=f'Min R: {params.min_radius:.1f}m')
    ax4.set_xlabel('Distance (m)')
    ax4.set_ylabel('Radius (m)')
    ax4.set_title('Turn Radius')
    ax4.legend(loc='upper right')
    ax4.grid(True, alpha=0.3)
    ax4.set_ylim(0, min(100, max(radii_display) * 1.2))
    
    # Plot 5: Curvature
    ax5 = axes[1, 1]
    ax5.plot(distances, geom.curvatures, 'c-', linewidth=2)
    ax5.axhline(y=0, color='gray', linestyle='-', alpha=0.5)
    ax5.set_xlabel('Distance (m)')
    ax5.set_ylabel('Curvature (1/m)')
    ax5.set_title('Curvature Profile')
    ax5.grid(True, alpha=0.3)
    
    # Plot 6: X-Y Track with speed color
    ax6 = axes[1, 2]
    scatter = ax6.scatter(geom.x, geom.y, c=speeds_kph, cmap='plasma', s=10)
    ax6.plot(geom.x[0], geom.y[0], 'go', markersize=10, label='Start')
    ax6.plot(geom.x[-1], geom.y[-1], 'rs', markersize=10, label='End')
    ax6.set_xlabel('X (m)')
    ax6.set_ylabel('Y (m)')
    ax6.set_title('Track Layout (colored by speed)')
    ax6.axis('equal')
    ax6.legend(loc='upper right')
    cbar = plt.colorbar(scatter, ax=ax6)
    cbar.set_label('Speed (kph)')
    
    plt.tight_layout()
    
    if show:
        plt.show()


def plot_overlay_comparison(all_results: List[SimulationResults]):
    """
    Create overlay comparison plots across all corners.
    """
    sns.set_theme(style="darkgrid", context="notebook")
    
    fig, axes = plt.subplots(2, 3, figsize=(16, 10))
    fig.suptitle('Corner Archetypes Comparison', fontsize=14, fontweight='bold')
    
    colors = plt.cm.tab10(np.linspace(0, 1, len(all_results)))
    
    # Normalize distances to percentage for comparison
    for idx, results in enumerate(all_results):
        label = f"{results.params.corner_type.value}"
        color = colors[idx]
        
        # Normalize distance to 0-100%
        dist_norm = results.geometry.distances / results.geometry.total_length * 100
        speeds_kph = results.final_speeds * 3.6
        
        # Plot 1: Lateral G
        axes[0, 0].plot(dist_norm, results.g_lat, color=color, linewidth=1.5, label=label)
        
        # Plot 2: Longitudinal G
        axes[0, 1].plot(dist_norm, results.g_long, color=color, linewidth=1.5, label=label)
        
        # Plot 3: Speed
        axes[0, 2].plot(dist_norm, speeds_kph, color=color, linewidth=1.5, label=label)
        
        # Plot 4: Radius (capped)
        radii_display = np.clip(results.geometry.radii, 0, 50)
        axes[1, 0].plot(dist_norm, radii_display, color=color, linewidth=1.5, label=label)
        
        # Plot 5: Curvature
        axes[1, 1].plot(dist_norm, results.geometry.curvatures, color=color, linewidth=1.5, label=label)
    
    # Configure axes
    axes[0, 0].set_xlabel('Distance (%)')
    axes[0, 0].set_ylabel('Lateral G')
    axes[0, 0].set_title('Lateral Acceleration')
    axes[0, 0].legend(fontsize=8, loc='upper right')
    axes[0, 0].grid(True, alpha=0.3)
    
    axes[0, 1].set_xlabel('Distance (%)')
    axes[0, 1].set_ylabel('Longitudinal G')
    axes[0, 1].set_title('Longitudinal Acceleration')
    axes[0, 1].axhline(y=0, color='gray', linestyle='-', alpha=0.5)
    axes[0, 1].grid(True, alpha=0.3)
    
    axes[0, 2].set_xlabel('Distance (%)')
    axes[0, 2].set_ylabel('Speed (kph)')
    axes[0, 2].set_title('Speed Profile')
    axes[0, 2].grid(True, alpha=0.3)
    
    axes[1, 0].set_xlabel('Distance (%)')
    axes[1, 0].set_ylabel('Radius (m)')
    axes[1, 0].set_title('Turn Radius')
    axes[1, 0].set_ylim(0, 50)
    axes[1, 0].grid(True, alpha=0.3)
    
    axes[1, 1].set_xlabel('Distance (%)')
    axes[1, 1].set_ylabel('Curvature (1/m)')
    axes[1, 1].set_title('Curvature')
    axes[1, 1].axhline(y=0, color='gray', linestyle='-', alpha=0.5)
    axes[1, 1].grid(True, alpha=0.3)
    
    # Plot 6: All tracks overlaid (normalized)
    ax6 = axes[1, 2]
    for idx, results in enumerate(all_results):
        color = colors[idx]
        # Normalize track to start at origin
        x_norm = results.geometry.x - results.geometry.x[0]
        y_norm = results.geometry.y - results.geometry.y[0]
        ax6.plot(x_norm, y_norm, color=color, linewidth=1.5, 
                 label=results.params.corner_type.value)
    ax6.set_xlabel('X (m)')
    ax6.set_ylabel('Y (m)')
    ax6.set_title('Track Layouts (aligned at start)')
    ax6.axis('equal')
    ax6.grid(True, alpha=0.3)
    
    plt.tight_layout()


def plot_summary_bars(all_results: List[SimulationResults]):
    """Create bar chart summary of key metrics."""
    sns.set_theme(style="darkgrid", context="notebook")
    
    names = [r.params.corner_type.value for r in all_results]
    min_speeds = [r.min_speed_kph for r in all_results]
    times = [r.corner_time for r in all_results]
    peak_g_lats = [r.peak_g_lat for r in all_results]
    
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))
    fig.suptitle('Corner Performance Summary', fontsize=14, fontweight='bold')
    
    x = np.arange(len(names))
    
    # Minimum speed
    axes[0].bar(x, min_speeds, color='tab:blue')
    axes[0].set_xticks(x)
    axes[0].set_xticklabels(names, rotation=45, ha='right')
    axes[0].set_ylabel('Minimum Speed (kph)')
    axes[0].set_title('Minimum Corner Speed')
    
    # Corner time
    axes[1].bar(x, times, color='tab:orange')
    axes[1].set_xticks(x)
    axes[1].set_xticklabels(names, rotation=45, ha='right')
    axes[1].set_ylabel('Time (s)')
    axes[1].set_title('Corner Time')
    
    # Peak lateral G
    axes[2].bar(x, peak_g_lats, color='tab:green')
    axes[2].set_xticks(x)
    axes[2].set_xticklabels(names, rotation=45, ha='right')
    axes[2].set_ylabel('Peak Lateral G')
    axes[2].set_title('Peak Lateral Acceleration')
    
    plt.tight_layout()


def print_summary_table(all_results: List[SimulationResults]):
    """Print a summary table of all corner results."""
    print("\n" + "="*100)
    print("CORNER ARCHETYPES SUMMARY")
    print("="*100)
    print(f"{'Corner Type':<20} {'Min R':>8} {'Angle':>8} {'Length':>8} {'Min Spd':>10} "
          f"{'Avg Spd':>10} {'Time':>8} {'Peak Glat':>10}")
    print(f"{'':20} {'(m)':>8} {'(deg)':>8} {'(m)':>8} {'(kph)':>10} "
          f"{'(kph)':>10} {'(s)':>8} {'(g)':>10}")
    print("-"*100)
    
    for r in all_results:
        print(f"{r.params.corner_type.value:<20} "
              f"{r.params.min_radius:>8.1f} "
              f"{np.degrees(r.params.turn_angle):>8.0f} "
              f"{r.geometry.total_length:>8.1f} "
              f"{r.min_speed_kph:>10.1f} "
              f"{r.avg_speed_kph:>10.1f} "
              f"{r.corner_time:>8.2f} "
              f"{r.peak_g_lat:>10.2f}")
    
    print("="*100 + "\n")


# =============================================================================
# CORNER DEFINITIONS
# =============================================================================

def create_fs_corner_archetypes() -> List[CornerParameters]:
    """
    Create the 8 Formula Student corner archetypes with realistic parameters.
    
    Returns:
        List of CornerParameters for each archetype
    """
    corners = [
        # 1. Hairpin - Tight U-turn (9m outside diameter = 4.5m outside radius)
        # With 3m track width, center radius ~3m
        CornerParameters(
            name="Hairpin Turn",
            corner_type=CornerType.HAIRPIN,
            turn_angle=np.pi,  # 180 degrees
            min_radius=4.5,  # Tight hairpin
            max_radius=4.5,
            radius_profile=RadiusProfile.CONSTANT,
            entry_straight=15.0,
            exit_straight=15.0,
            direction=1
        ),
        
        # 2. 90-degree corner - Standard right angle
        CornerParameters(
            name="90-Degree Corner",
            corner_type=CornerType.NINETY_DEGREE,
            turn_angle=np.pi / 2,  # 90 degrees
            min_radius=7.0,
            max_radius=7.0,
            radius_profile=RadiusProfile.CONSTANT,
            entry_straight=20.0,
            exit_straight=20.0,
            direction=-1
        ),
        
        # 3. Medium-speed sweeper - Longer radius constant
        CornerParameters(
            name="Medium Sweeper",
            corner_type=CornerType.MEDIUM_SWEEPER,
            turn_angle=np.pi / 3,  # 60 degrees
            min_radius=15.0,
            max_radius=15.0,
            radius_profile=RadiusProfile.CONSTANT,
            entry_straight=25.0,
            exit_straight=25.0,
            direction=1
        ),
        
        # 4. High-speed corner - Fast, gentle curve
        CornerParameters(
            name="High-Speed Corner",
            corner_type=CornerType.HIGH_SPEED,
            turn_angle=np.pi / 4,  # 45 degrees
            min_radius=22.0,  # Up to 25m allowed
            max_radius=22.0,
            radius_profile=RadiusProfile.CONSTANT,
            entry_straight=30.0,
            exit_straight=30.0,
            direction=-1
        ),
        
        # 5. Decreasing-radius corner - Opens then tightens
        CornerParameters(
            name="Decreasing Radius",
            corner_type=CornerType.DECREASING_RADIUS,
            turn_angle=np.pi / 2,  # 90 degrees
            min_radius=6.0,  # Tightens to this
            max_radius=18.0,  # Starts at this
            radius_profile=RadiusProfile.DECREASING,
            entry_straight=25.0,
            exit_straight=15.0,
            direction=1
        ),
        
        # 6. Increasing-radius corner - Tight entry, opens up
        CornerParameters(
            name="Increasing Radius",
            corner_type=CornerType.INCREASING_RADIUS,
            turn_angle=np.pi / 2,  # 90 degrees
            min_radius=6.0,  # Starts at this
            max_radius=18.0,  # Opens to this
            radius_profile=RadiusProfile.INCREASING,
            entry_straight=15.0,
            exit_straight=25.0,
            direction=-1
        ),
        
        # 7. Chicane - S-bend left-right
        CornerParameters(
            name="Chicane",
            corner_type=CornerType.CHICANE,
            turn_angle=np.pi / 4,  # 45 degrees each way
            min_radius=8.0,
            max_radius=8.0,
            radius_profile=RadiusProfile.CONSTANT,
            entry_straight=20.0,
            exit_straight=20.0,
            secondary_angle=np.pi / 4,
            secondary_radius=8.0,
            mid_straight=5.0,
            direction=1
        ),
        
        # 8. Double-apex corner - Two apexes in one turn
        CornerParameters(
            name="Double Apex",
            corner_type=CornerType.DOUBLE_APEX,
            turn_angle=2 * np.pi / 3,  # 120 degrees total
            min_radius=7.0,  # Apex radius
            max_radius=15.0,  # Mid-section radius
            radius_profile=RadiusProfile.CONSTANT,
            entry_straight=20.0,
            exit_straight=20.0,
            secondary_radius=8.0,
            mid_straight=8.0,
            direction=1
        ),
    ]
    
    return corners


# =============================================================================
# MAIN
# =============================================================================

def load_config(config_path: str) -> dict:
    """Load configuration from JSON file."""
    with open(config_path, 'r') as f:
        return json.load(f)


def main():
    """Main entry point for corner archetypes simulation."""
    logger.info("="*60)
    logger.info("CORNER ARCHETYPES SIMULATION")
    logger.info("="*60)
    
    # Load configuration
    config_path = os.path.join(REPO_ROOT, "config.json")
    logger.info(f"Loading config from: {config_path}")
    config = load_config(config_path)
    
    # Create vehicle
    logger.info("Creating vehicle from configuration...")
    try:
        vehicle = create_vehicle(config)
        logger.info(f"Vehicle loaded: {vehicle.params.name}, mass: {vehicle.params.mass} kg")
    except Exception as e:
        logger.error(f"Error loading vehicle: {e}")
        return
    
    # Create corner archetypes
    corners = create_fs_corner_archetypes()
    logger.info(f"Created {len(corners)} corner archetypes")
    
    # Run simulations
    all_results = []
    for params in corners:
        try:
            results = simulate_corner(params, vehicle, config)
            all_results.append(results)
        except Exception as e:
            logger.error(f"Error simulating {params.name}: {e}")
            import traceback
            traceback.print_exc()
            continue
    
    if not all_results:
        logger.error("No successful simulations. Exiting.")
        return
    
    # Print summary table
    print_summary_table(all_results)
    
    # Generate plots
    logger.info("Generating visualization plots...")
    
    # Individual corner plots
    for results in all_results:
        plot_corner_results(results)
    
    # Overlay comparison
    plot_overlay_comparison(all_results)
    
    # Summary bar charts
    plot_summary_bars(all_results)
    
    # Show all plots
    logger.info("Displaying plots...")
    plt.show()
    
    logger.info("Corner archetypes simulation complete!")


if __name__ == "__main__":
    main()
