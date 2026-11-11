# This script takes an input of an inner circle diameter, outer circle diameter, and track width
# and generates a skidpad track layout in the format of cartesian coordinates.
# The output is a txt file compatible with the track loader used in the simulator.
# NOTE: This skidpad doesn't seem to converge very well with the sim....The sim seems better suited to non-consistent corners

import numpy as np
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))

# Constants for Formula Student skidpad (from rules)
INNER_CIRCLE_DIAMETER = 15.25  # meters
OUTER_CIRCLE_DIAMETER = 21.25  # meters
TRACK_WIDTH = 3.0  # meters
CIRCLE_CENTER_DISTANCE = 18.25  # meters (distance between circle centers)

# Output configuration
OUTPUT_FILENAME = "SkidpadF26.txt"
OUTPUT_DIR = os.path.join(REPO_ROOT, "datasets", "tracks")
POINTS_PER_CIRCLE = 100  # Number of points to generate per circle


def calculate_centerline_radius(inner_diameter: float, outer_diameter: float) -> float:
    """
    Calculate the radius of the centerline (driving path center).
    The centerline is the middle of the track width between inner and outer circles.
    
    Args:
        inner_diameter: Diameter of the inner circle
        outer_diameter: Diameter of the outer circle
        
    Returns:
        Radius of the centerline
    """
    inner_radius = inner_diameter / 2
    outer_radius = outer_diameter / 2
    centerline_radius = (inner_radius + outer_radius) / 2
    return centerline_radius


def generate_circle_points(center_x: float, center_y: float, radius: float, 
                           start_angle: float, end_angle: float, 
                           num_points: int, clockwise: bool = True) -> np.ndarray:
    """
    Generate points along a circular arc.
    
    Args:
        center_x: X coordinate of circle center
        center_y: Y coordinate of circle center
        radius: Radius of the circle
        start_angle: Starting angle in radians (0 = positive x-axis)
        end_angle: Ending angle in radians
        num_points: Number of points to generate
        clockwise: If True, generate points in clockwise direction
        
    Returns:
        numpy array of shape (num_points, 2) with x, y coordinates
    """
    if clockwise:
        # For clockwise, we go from start_angle decreasing to end_angle
        angles = np.linspace(start_angle, end_angle, num_points)
    else:
        # For counter-clockwise, angles increase
        angles = np.linspace(start_angle, end_angle, num_points)
    
    x = center_x + radius * np.cos(angles)
    y = center_y + radius * np.sin(angles)
    
    return np.column_stack((x, y))


def generate_entry_exit_path(start_point: np.ndarray, end_point: np.ndarray, 
                              num_points: int) -> np.ndarray:
    """
    Generate a straight line path between two points.
    
    Args:
        start_point: Starting point (x, y)
        end_point: Ending point (x, y)
        num_points: Number of points to generate
        
    Returns:
        numpy array of shape (num_points, 2) with x, y coordinates
    """
    x = np.linspace(start_point[0], end_point[0], num_points)
    y = np.linspace(start_point[1], end_point[1], num_points)
    return np.column_stack((x, y))


def generate_skidpad_centerline(inner_diameter: float = INNER_CIRCLE_DIAMETER,
                                 outer_diameter: float = OUTER_CIRCLE_DIAMETER,
                                 center_distance: float = CIRCLE_CENTER_DISTANCE,
                                 points_per_circle: int = POINTS_PER_CIRCLE) -> np.ndarray:
    """
    Generate the complete skidpad centerline coordinates.
    
    The path follows a figure-8 pattern:
    1. Enter from the bottom (straight path)
    2. Go around the RIGHT circle CLOCKWISE (one full lap)
    3. Cross to the LEFT circle
    4. Go around the LEFT circle COUNTER-CLOCKWISE (one full lap)
    5. Exit from the bottom (straight path)
    
    The coordinate system has:
    - Origin at the midpoint between the two circle centers (the start/finish line crossing)
    - Right circle center at (center_distance/2, 0)
    - Left circle center at (-center_distance/2, 0)
    
    Args:
        inner_diameter: Diameter of the inner boundary circle
        outer_diameter: Diameter of the outer boundary circle
        center_distance: Distance between the two circle centers
        points_per_circle: Number of points to generate for each circle
        
    Returns:
        numpy array of shape (N, 2) with x, y coordinates of the centerline
    """
    centerline_radius = calculate_centerline_radius(inner_diameter, outer_diameter)
    
    # Define circle centers
    right_center_x = center_distance / 2
    left_center_x = -center_distance / 2
    center_y = 0
    
    # Entry/exit path length (from bottom, tangent to where circles meet)
    entry_length = 0.0  # meters of entry/exit straight
    entry_points = 0
    
    all_points = []
    
    # 1. Entry path - straight from bottom to the crossing point
    # The entry is at the center (x=0), coming from negative y
    entry_start = np.array([0, -entry_length])
    entry_end = np.array([0, 0])
    entry_path = generate_entry_exit_path(entry_start, entry_end, entry_points)
    all_points.append(entry_path[:-1])  # Exclude last point to avoid duplication
    
    # 2. Right circle - clockwise (starting from left side of right circle, going down first)
    # Starting at the center crossing point (x=0, which is the left side of the right circle)
    # For clockwise motion starting from the left of the circle (angle = π), 
    # we go: π → 0 → -π (full circle back to start)
    right_circle_angles = np.linspace(np.pi, -np.pi, points_per_circle)
    right_circle = generate_circle_points(right_center_x, center_y, centerline_radius,
                                          np.pi, -np.pi, points_per_circle, clockwise=True)
    all_points.append(right_circle[:-1])  # Exclude last point (same as first)
    
    # 3. Cross back through center - the path naturally connects at x=0, y=0
    # Actually, after completing the right circle, we're back at the crossing point
    # and continue to the left circle
    
    # 4. Left circle - counter-clockwise (starting from right side of left circle)
    # Starting at x=0 (right side of left circle), going up first
    # For counter-clockwise starting from angle=0, we go: 0 → 2π
    left_circle = generate_circle_points(left_center_x, center_y, centerline_radius,
                                         0, 2*np.pi, points_per_circle, clockwise=False)
    all_points.append(left_circle[:-1])  # Exclude last point (same as first)
    
    # 5. Exit path - straight from crossing point to bottom
    exit_start = np.array([0, 0])
    exit_end = np.array([0, -entry_length])
    exit_path = generate_entry_exit_path(exit_start, exit_end, entry_points)
    all_points.append(exit_path)
    
    # Combine all path segments
    centerline = np.vstack(all_points)
    
    return centerline


def write_track_file(coordinates: np.ndarray, output_path: str, 
                     track_name: str = "Formula Student Skidpad"):
    """
    Write the track coordinates to a file in the expected format.
    
    Format: x y z q (tab-separated)
    - z and q are set to 0 as per the requirement
    
    Args:
        coordinates: numpy array of shape (N, 2) with x, y coordinates
        output_path: Full path to the output file
        track_name: Name of the track for the header
    """
    with open(output_path, 'w') as f:
        # Write header
        f.write(": x y z q\n")
        f.write("#\n")
        f.write("# \n")
        f.write(f"# {track_name.upper()} TRACK COORDINATES\n")
        f.write("#\n")
        f.write("# Generated by skidpadCreator.py\n")
        f.write("#\n")
        f.write("# Inner Circle Diameter: {:.2f}m\n".format(INNER_CIRCLE_DIAMETER))
        f.write("# Outer Circle Diameter: {:.2f}m\n".format(OUTER_CIRCLE_DIAMETER))
        f.write("# Track Width: {:.2f}m\n".format(TRACK_WIDTH))
        f.write("# Centerline Radius: {:.3f}m\n".format(
            calculate_centerline_radius(INNER_CIRCLE_DIAMETER, OUTER_CIRCLE_DIAMETER)))
        f.write("#\n")
        f.write("# x y z q\n")
        
        # Write coordinates
        for x, y in coordinates:
            f.write(f"{x:.7f}\t{y:.7f}\t0\t0\n")
    
    print(f"Track file written to: {output_path}")
    print(f"Total points: {len(coordinates)}")


def visualize_skidpad(coordinates: np.ndarray, inner_diameter: float, 
                      outer_diameter: float, center_distance: float):
    """
    Visualize the generated skidpad for verification.
    
    Args:
        coordinates: numpy array of shape (N, 2) with x, y coordinates
        inner_diameter: Diameter of the inner boundary circle
        outer_diameter: Diameter of the outer boundary circle
        center_distance: Distance between the two circle centers
    """
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not installed, skipping visualization")
        return
    
    fig, ax = plt.subplots(1, 1, figsize=(12, 10))
    
    # Plot the centerline path
    ax.plot(coordinates[:, 0], coordinates[:, 1], 'b-', linewidth=2, label='Centerline')
    ax.plot(coordinates[0, 0], coordinates[0, 1], 'go', markersize=10, label='Start')
    ax.plot(coordinates[-1, 0], coordinates[-1, 1], 'ro', markersize=10, label='End')
    
    # Draw the boundary circles
    inner_radius = inner_diameter / 2
    outer_radius = outer_diameter / 2
    right_center = center_distance / 2
    left_center = -center_distance / 2
    
    theta = np.linspace(0, 2*np.pi, 100)
    
    # Right circle boundaries
    ax.plot(right_center + inner_radius * np.cos(theta), 
            inner_radius * np.sin(theta), 'r--', alpha=0.5, label='Inner boundary')
    ax.plot(right_center + outer_radius * np.cos(theta), 
            outer_radius * np.sin(theta), 'g--', alpha=0.5, label='Outer boundary')
    
    # Left circle boundaries
    ax.plot(left_center + inner_radius * np.cos(theta), 
            inner_radius * np.sin(theta), 'r--', alpha=0.5)
    ax.plot(left_center + outer_radius * np.cos(theta), 
            outer_radius * np.sin(theta), 'g--', alpha=0.5)
    
    # Mark circle centers
    ax.plot(right_center, 0, 'k+', markersize=15, markeredgewidth=2)
    ax.plot(left_center, 0, 'k+', markersize=15, markeredgewidth=2)
    ax.plot(0, 0, 'kx', markersize=15, markeredgewidth=2, label='Start/Finish Line')
    
    ax.set_xlabel('X (m)')
    ax.set_ylabel('Y (m)')
    ax.set_title('Formula Student Skidpad - Centerline Path')
    ax.set_aspect('equal')
    ax.legend()
    ax.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.show()


def main():
    """Main function to generate the skidpad track file."""
    print("=" * 60)
    print("Formula Student Skidpad Creator")
    print("=" * 60)
    
    # Calculate and display parameters
    centerline_radius = calculate_centerline_radius(INNER_CIRCLE_DIAMETER, OUTER_CIRCLE_DIAMETER)
    print(f"\nParameters:")
    print(f"  Inner Circle Diameter: {INNER_CIRCLE_DIAMETER} m")
    print(f"  Outer Circle Diameter: {OUTER_CIRCLE_DIAMETER} m")
    print(f"  Track Width: {TRACK_WIDTH} m")
    print(f"  Circle Center Distance: {CIRCLE_CENTER_DISTANCE} m")
    print(f"  Centerline Radius: {centerline_radius:.3f} m")
    
    # Generate the skidpad centerline
    print("\nGenerating skidpad centerline...")
    centerline = generate_skidpad_centerline()
    
    # Create output directory if it doesn't exist
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    # Write the track file
    output_path = os.path.join(OUTPUT_DIR, OUTPUT_FILENAME)
    write_track_file(centerline, output_path)
    
    # Visualize the result
    print("\nDisplaying visualization...")
    visualize_skidpad(centerline, INNER_CIRCLE_DIAMETER, OUTER_CIRCLE_DIAMETER, 
                      CIRCLE_CENTER_DISTANCE)
    
    print("\nDone!")


if __name__ == "__main__":
    main()