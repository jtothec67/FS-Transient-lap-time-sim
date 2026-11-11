import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns

from ..results import LapTimeResults

def plot_lap_time_results(results):
    track = results.track
    final_speeds = results.final_speeds
    corner_speeds = results.corner_speeds
    lap_time = results.lap_time
    g_lat_channel = results.g_lat_channel
    g_long_channel = results.g_long_channel

    distances = [p.distance for p in track.points]
    x_coords = [p.x for p in track.points]
    y_coords = [p.y for p in track.points]
    v_car_kph = np.array(final_speeds) * 3.6  # Convert m/s to kph
    corner_speeds_kph = np.array(corner_speeds) * 3.6  # Convert m/s to kph

    # --- Plot 1: Speed Profile with gLat and gLong traces ---
    sns.set_theme(style="darkgrid", context="notebook")
    fig1, ax1 = plt.subplots(figsize=(12, 6))
    ax1.plot(distances, v_car_kph, label='v_car (kph)', linewidth=2, color='tab:blue')
    ax1.plot(distances, corner_speeds_kph, '--', label='Theoretical v_car limit', alpha=0.7, color='tab:gray')
    ax1.set_xlabel('Distance along track (m)')
    ax1.set_ylabel('Speed (kph)')
    ax1.set_ylim(0, 150)  # Limit left axis to 150 kph
    ax1.set_title(f'Lap Time: {lap_time:.2f} s\nLap Time Sim telemetry')
    ax1.legend(loc='upper left')
    # No grid for plot 1

    # Create second y-axis for gLat and gLong
    ax2 = ax1.twinx()
    ax2.plot(distances[1:], g_lat_channel, label='gLat', color='tab:green')
    ax2.plot(distances[1:], g_long_channel, label='gLong', color='tab:orange')
    ax2.set_ylabel('Acceleration (g)')
    ax2.set_ylim(-10, 5)
    ax2.legend(loc='upper right')
    fig1.tight_layout()

    # --- Plot 2: G-G-V Diagram ---
    fig2, ax3 = plt.subplots(figsize=(8, 8))
    scatter_g = ax3.scatter(g_lat_channel, g_long_channel, c=v_car_kph[1:], cmap='viridis', s=20)
    ax3.set_xlabel('Lateral Acceleration (g)')
    ax3.set_ylabel('Longitudinal Acceleration (g)')
    ax3.set_title('G-G-V Diagram', fontsize=18)
    cbar_g = fig2.colorbar(scatter_g, ax=ax3)
    cbar_g.set_label('Speed (kph)')
    ax3.grid(True, which='both', linestyle='--', alpha=0.7)
    ax3.set_xlim(min(g_lat_channel)-1, max(g_lat_channel)+1)
    ax3.set_ylim(min(g_long_channel)-1, max(g_long_channel)+1)
    fig2.tight_layout()

    # --- Plot 3: 2D Track Map with v_car Colour Gradient ---
    fig3, ax4 = plt.subplots(figsize=(10, 8))
    scatter_track = ax4.scatter(x_coords, y_coords, c=v_car_kph, cmap='plasma', s=8)
    ax4.set_xlabel('X (m)')
    ax4.set_ylabel('Y (m)')
    ax4.set_title('2D Track Map: v_car (kph) Colour Gradient')
    cbar_track = fig3.colorbar(scatter_track, ax=ax4)
    cbar_track.set_label('Speed (kph)')
    ax4.axis('equal')
    fig3.tight_layout()

    # Show all plots at once
    plt.show()
