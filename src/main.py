import json
import os

def load_config(config_path):
    with open(config_path, 'r') as f:
        return json.load(f)

config_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../config.json'))
config = load_config(config_path)


def main():
    # Import modules
    from track.track import load_track
    from vehicle.vehicle import create_vehicle
    from simulator.simulator import run_lap_time_simulation

    # Load track data
    print("Using track file_path:", config["track"]["file_path"])
    try:
        track = load_track(config["track"]["file_path"], config.get("debug_mode", False))
        print(f"Loaded track with {len(track.points)} points, total length: {track.total_length:.2f} m")
    except Exception as e:
        print("Error loading track:", e)
        return

    # Load vehicle parameters
    try:
        vehicle = create_vehicle(config)
        print(f"Loaded vehicle: {vehicle.params.name}, mass: {vehicle.params.mass} kg")
    except Exception as e:
        print("Error loading vehicle:", e)
        return

    # Initialise simulation loop
    try:
        run_lap_time_simulation(track, vehicle, config)
    except Exception as e:
        print("Error during simulation:", e)
        return

if __name__ == "__main__":
    main()