
import numpy as np
import logging
import matplotlib.pyplot as plt
from importlib import import_module

from .util.calcSpeedProfile import compute_speed_profile
from .util.results import LapTimeResults
from .util.transientDynamics import run_transient_replay

logger = logging.getLogger(__name__)


def _plot_lap_time_results(results) -> None:
    try:
        plot_module = import_module(".util.prettyGraphs.lapTimeResults", __package__)
    except ModuleNotFoundError:
        logger.warning("Plotting extras are unavailable in this runtime; skipping lap-time plots.")
        return

    plot_module.plot_lap_time_results(results)

def run_lap_time_simulation(track, vehicle, config, display=True):
    """Initialize and run a lap time simulation for the whole track."""
    logger.info("Starting lap time simulation...")
    # Run the lap time sim, given the track and vehicle
    final_speeds, corner_speeds, diagnostics = compute_speed_profile(track, vehicle, config)
    
    transient_results = run_transient_replay(track, vehicle, final_speeds)

    for result in transient_results[::max(1, len(transient_results) // 10)]:
        (
            distance,
            actual_yaw,
            required_yaw,
            x,
            y,
            actual_speed,
            target_speed,
            time,
            throttle,
            brake,
            path_error
        ) = result

        print(
            f"Distance: {distance:.1f}m | "
            f"Actual Speed: {actual_speed * 3.6:.1f}km/h | "
            f"Target Speed: {target_speed * 3.6:.1f}km/h | "
            f"Yaw Rate: {actual_yaw:.3f}rad/s | "
            f"Throttle: {throttle:.2f} | "
            f"Brake: {brake:.2f} | "
            f"Path Error: {path_error:.2f}m"
        )

    if transient_results:
        print(f"Replay elapsed time: {transient_results[-1][7]:.2f}s")
        print(f"Last recorded distance: {transient_results[-1][0]:.1f}m")

    # Original track coordinates
    track_x = [point.x for point in track.points]
    track_y = [point.y for point in track.points]

    # Calculated vehicle trajectory
    vehicle_x = [result[3] for result in transient_results]
    vehicle_y = [result[4] for result in transient_results]

    track_x = [point.x for point in track.points]
    track_y = [point.y for point in track.points]

    vehicle_x = [result[3] for result in transient_results]
    vehicle_y = [result[4] for result in transient_results]

    distances = [result[0] for result in transient_results]
    throttles = [result[8] for result in transient_results]
    brakes = [result[9] for result in transient_results]
    path_errors = [result[10] for result in transient_results]
    actual_speeds = [result[5] * 3.6 for result in transient_results]
    target_speeds = [result[6] * 3.6 for result in transient_results]

    plt.figure()

    plt.plot(track_x, track_y, label="Original Track")
    plt.plot(vehicle_x, vehicle_y, label="Transient Vehicle")

    plt.xlabel("X Position (m)")
    plt.ylabel("Y Position (m)")
    plt.title("Transient Vehicle Trajectory")
    plt.axis("equal")
    plt.legend()
    plt.grid(True)

    plt.figure()

    plt.subplot(3, 1, 1)
    plt.plot(distances, actual_speeds, label="Actual Speed")
    plt.plot(distances, target_speeds, label="Target Speed")
    plt.ylabel("Speed (km/h)")
    plt.title("Speed Trace")
    plt.legend()
    plt.grid(True)

    plt.subplot(3, 1, 2)
    plt.plot(distances, throttles, label="Throttle")
    plt.plot(distances, brakes, label="Brake")
    plt.ylabel("Input")
    plt.title("Throttle / Brake Trace")
    plt.legend()
    plt.grid(True)

    plt.subplot(3, 1, 3)
    plt.plot(distances, path_errors, label="Path Error")
    plt.xlabel("Distance Along Track (m)")
    plt.ylabel("Error (m)")
    plt.title("Path Error Trace")
    plt.legend()
    plt.grid(True)

    plt.tight_layout()

    plt.show()

    # Compute lap time and g-forces based on final speeds
    lap_time = 0.0
    g_lat_channel = []
    g_long_channel = []
    normal_load_per_tyre = diagnostics.get('forward_normal_load_per_tyre', [])
    long_force_per_tyre = diagnostics.get('forward_net_long_force', [])
    lat_force_per_tyre = []
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
        g_lat = v_curr**2 * track.points[i].curvature / 9.81
        g_lat_channel.append(g_lat)
        if v_avg > 0:
            dt = ds / v_avg
            lap_time += dt
    logger.info(f"Estimated lap time: {lap_time:.2f} seconds")
    logger.info("Lap time simulation completed.")
    results = LapTimeResults(
        track=track,
        final_speeds=np.array(final_speeds),
        corner_speeds=np.array(corner_speeds),
        lap_time=lap_time,
        g_lat_channel=g_lat_channel,
        g_long_channel=g_long_channel,
        normal_load_per_tyre=normal_load_per_tyre,
        long_force_per_tyre=long_force_per_tyre,
        lat_force_per_tyre=lat_force_per_tyre,
        diagnostics=diagnostics,
    )
    if display:
        _plot_lap_time_results(results)
    return results
