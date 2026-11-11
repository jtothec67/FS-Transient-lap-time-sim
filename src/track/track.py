import logging
import os
import numpy as np
from importlib import import_module
from dataclasses import dataclass

logger = logging.getLogger(__name__)


def _show_debug_track_plot(x: np.ndarray, y: np.ndarray, z: np.ndarray) -> None:
    try:
        sns = import_module("seaborn")
        plt = import_module("matplotlib.pyplot")
    except ModuleNotFoundError:
        logger.warning("Plotting extras are unavailable in this runtime; skipping track debug plot.")
        return

    sns.set_theme(style="darkgrid", context="notebook")

    fig = plt.figure()
    ax = fig.add_subplot(111, projection='3d')
    ax.plot(x, y, z, label='Track 3D Path')
    ax.set_xlabel('X (m)')
    ax.set_ylabel('Y (m)')
    ax.set_zlabel('Z (m)')
    ax.set_title('Track 3D Map')
    ax.legend()
    plt.show()

@dataclass  # using dataclasses removes the need for constructor boilerplate
class TrackPoint:
    """Represents a single point on the track with all relevant geometric properties."""
    distance: float
    x: float    
    y: float
    z: float
    curvature: float
    heading: float
    elevation_angle: float

class Track:
    """
    Track representation with geometric properties for lap time simulation.
    
    Attributes:
        points: List of TrackPoint objects
        total_length: Total track length in meters
        is_closed: Whether the track forms a closed loop
    """
    def __init__(self, points: list[TrackPoint], is_closed: bool = True):
        self.points = points
        self.is_closed = is_closed
        self.total_length = points[-1].distance if points else 0.0

def load_track(file_path: str, debug_mode) -> Track:
    """
    Load track format (x, y, z, q coordinates).
    
    Args:
        file_path: Path to track file
        
    Returns:
        Track object with computed geometric properties
    """
    abs_path = os.path.abspath(file_path)
    logger.info(f"Loading track from {abs_path}")
    
    # Read the track data, skipping comment lines
    data = []
    with open(abs_path, 'r') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and not line.startswith(':'):
                try:
                    parts = line.split()
                    if len(parts) >= 3:
                        x, y, z = float(parts[0]), float(parts[1]), float(parts[2])
                        data.append((x, y, z))
                except (ValueError, IndexError):
                    continue
        # Convert to numpy arrays for efficient computation
        coords = np.array(data)
        x, y, z = coords[:, 0], coords[:, 1], coords[:, 2]

        # Calculate distances along track
        distances = _calc_cum_dist(x, y, z)

        # Calculate curvature using finite differences
        curvatures = _calc_curvature(x, y, distances)

        # Calculate headings
        headings = _calc_headings(x, y)

        # Calculate elevation angles
        elevation_angles = _calc_elevation_angles(distances, z)

        # Create TrackPoint objects
        points = []
        for i in range(len(x)):
            point = TrackPoint(
                distance=distances[i],
                x=x[i],
                y=y[i],
                z=z[i],
                curvature=curvatures[i],
                heading=headings[i],
                elevation_angle=elevation_angles[i]
            )
            points.append(point)

        logger.info(f"Loaded track with {len(points)} points, total length: {distances[-1]:.1f}m")

        if debug_mode is True:
            _show_debug_track_plot(x, y, z)

        return Track(points, is_closed=True)

    if not data:
        raise ValueError("No valid track data found in file")
    
def _calc_cum_dist(x: np.ndarray, y: np.ndarray, z: np.ndarray) -> np.ndarray:
    """
    Calculate cumulative distance along track from coordinate arrays.
    Returns: 1D array of cumulative distances starting from 0.
    Unit: meters
    """
    dx = np.diff(x)
    dy = np.diff(y)
    dz = np.diff(z)
    
    # 3D distance calculation
    segments_lengths = np.sqrt(dx**2 + dy**2 + dz**2)
    
    # Cumulative distance starting from 0
    distances = np.zeros(len(x))
    distances[1:] = np.cumsum(segments_lengths)
    
    return distances


def _calc_curvature(x: np.ndarray, y: np.ndarray, distances: np.ndarray) -> np.ndarray:
    """
    Calculate track curvature using the formula:
    κ = (x'y'' - y'x'') / (x'^2 + y'^2)^(3/2)
    
    Where primes indicate derivatives with respect to distance.
    Second derivatives ('') describe how the direction of the tangent vector changes.
    Sign convention: positive for left turns, negative for right turns.
        High curvature = tight turn.
        Low curvature = gentle turn or straight.

    Returns: 1D array of curvature values at each track point. 
    Unit: 1/m (inverse meters)
    """
    n = len(x)
    curvatures = np.zeros(n)
    
    # Use central differences for interior points
    for i in range(1, n-1):
        # First derivatives (tangent vector)
        ds_back = distances[i] - distances[i-1]
        ds_forward = distances[i+1] - distances[i]
        
        if ds_back > 0 and ds_forward > 0:
            dx_ds = (x[i+1] - x[i-1]) / (distances[i+1] - distances[i-1])
            dy_ds = (y[i+1] - y[i-1]) / (distances[i+1] - distances[i-1])
            
            # Second derivatives
            d2x_ds2 = ((x[i+1] - x[i]) / ds_forward - (x[i] - x[i-1]) / ds_back) / (0.5 * (ds_forward + ds_back))
            d2y_ds2 = ((y[i+1] - y[i]) / ds_forward - (y[i] - y[i-1]) / ds_back) / (0.5 * (ds_forward + ds_back))
            
            # Curvature calculation (preserve sign for turn direction)
            numerator = dx_ds * d2y_ds2 - dy_ds * d2x_ds2
            denominator = (dx_ds**2 + dy_ds**2)**(3/2)
            
            if denominator > 1e-10:
                curvatures[i] = numerator / denominator
    
    # Handle endpoints by copying nearest interior values
    curvatures[0] = curvatures[1] if n > 1 else 0.0
    curvatures[-1] = curvatures[-2] if n > 1 else 0.0
    
    return curvatures


def _calc_headings(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """
    Calculate track heading angles in radians.
    Returns:
    1D array of heading angles at each track point.
    Unit: radians (0 = East, π/2 = North, π = West, -π/2 = South)
    """
    n = len(x)
    headings = np.zeros(n)
    
    # Calculate heading as angle of tangent vector
    for i in range(n-1):
        dx = x[i+1] - x[i]
        dy = y[i+1] - y[i]
        headings[i] = np.arctan2(dy, dx)
    
    # Last point uses previous heading
    headings[-1] = headings[-2] if n > 1 else 0.0
    
    return headings


def _calc_elevation_angles(distances: np.ndarray, z: np.ndarray) -> np.ndarray:
    """
    Calculate elevation angles (grade) in radians.
    Returns:
    1D array of elevation angles at each track point.
    Unit: radians (positive = uphill, negative = downhill)
    """
    n = len(distances)
    elevation_angles = np.zeros(n)
    
    for i in range(n-1):
        ds = distances[i+1] - distances[i]
        dz = z[i+1] - z[i]
        if ds > 1e-10:
            elevation_angles[i] = np.arctan(dz / ds)
    
    elevation_angles[-1] = elevation_angles[-2] if n > 1 else 0.0
    
    return elevation_angles
