import numpy as np
import matplotlib.pyplot as plt
from vehicle import Vehicle

def plot_ggv_diagram(final_speeds, track, vehicle, mass):
    """
    Plot G-G-V diagram. For visibility, filter out near-zero lateral points
    and overlay theoretical friction ellipse.
    """
    g = 9.81
    n = len(final_speeds)

    a_lat = np.array([
        final_speeds[i]**2 * track.points[i].curvature / g
        for i in range(n)
    ])
    a_long = np.zeros(n)
    for i in range(1, n):
        ds = track.points[i].distance - track.points[i-1].distance
        if ds > 0:
            a_long[i] = (final_speeds[i]**2 - final_speeds[i-1]**2) / (2 * ds * g)

    speeds_kph = np.array(final_speeds) * 3.6

    fig, ax = plt.subplots(figsize=(8, 8))

    sc = ax.scatter(a_lat, a_long, c=speeds_kph, cmap='plasma', s=15, alpha=0.7)
    plt.colorbar(sc, ax=ax, label='Speed (kph)')

    # Overlay theoretical friction ellipse at peak tyre limit
    normal_load = vehicle.compute_static_normal_load()
    f_lat_peak = abs(vehicle.tyre_model.get_lateral_force(
        slip_angle=10.0, normal_load=normal_load)) * 4
    f_lon_peak = abs(vehicle.tyre_model.get_longitudinal_force(
        slip_ratio=12.0, normal_load=normal_load)) * 4
    a_lat_limit = f_lat_peak / (mass * g)
    a_lon_limit = f_lon_peak / (mass * g)

    theta = np.linspace(0, 2 * np.pi, 200)
    ax.plot(
        a_lat_limit * np.cos(theta),
        a_lon_limit * np.sin(theta),
        'r--', linewidth=1.5, alpha=0.6, label=f'Friction ellipse ({a_lat_limit:.2f}g / {a_lon_limit:.2f}g)'
    )

    ax.axhline(0, color='white', linewidth=0.5, linestyle='--')
    ax.axvline(0, color='white', linewidth=0.5, linestyle='--')
    ax.set_xlabel('Lateral Acceleration (g)', fontsize=17)
    ax.set_ylabel('Longitudinal Acceleration (g)', fontsize=17)
    ax.set_title('G-G-V Diagram', fontsize=20, fontweight='bold')
    ax.legend()
    plt.tight_layout()

# Example usage
if __name__ == "__main__":
    track = Track()
    vehicle = Vehicle()
    final_speeds = [10, 20, 30, 40, 50]
    mass = 1000  # kg
    plot_ggv_diagram(final_speeds, track, vehicle, mass)
