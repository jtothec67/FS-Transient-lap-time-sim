import json
import os
from typing import Any

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DEFAULT_OUTPUT_PATH = os.path.join(REPO_ROOT, "artifacts", "sweeps", "data.csv")

def load_config(config_path):
    with open(config_path, 'r') as f:
        return json.load(f)

config_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../config.json'))
config = load_config(config_path)


def _build_param_alias_map() -> dict[str, str]:
    """Build aliases from raw parameter JSON keys to vehicle.params attribute names."""
    alias_map: dict[str, str] = {}

    params_path = config.get("vehicle_parameters", "parameters.json")
    if not os.path.isabs(params_path):
        params_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", params_path))

    try:
        with open(params_path, "r") as f:
            data = json.load(f)
    except Exception:
        return alias_map

    for section, section_data in data.items():
        if section.startswith("_") or not isinstance(section_data, dict):
            continue
        for key in section_data.keys():
            alias_map[key] = key

    # Keep backwards-compatible naming differences between JSON key and dataclass field.
    alias_map["aero_cp"] = "aero_centre_of_pressure"

    return alias_map


def _coerce_values(raw_values: str, current_value: Any, steps: int) -> list[Any]:
    """Parse CLI values to match parameter type while preserving numeric range behavior."""
    raw_values = raw_values.strip()

    # Numeric scalar: preserve existing range syntax min,max + --steps.
    if isinstance(current_value, (int, float)) and not isinstance(current_value, bool):
        import numpy as np

        parts = [p.strip() for p in raw_values.split(",") if p.strip()]
        numeric_values = [float(v) for v in parts]
        if len(numeric_values) == 2 and steps > 1:
            return [float(v) for v in np.linspace(numeric_values[0], numeric_values[1], steps)]
        return numeric_values

    # Bool: accept true/false/1/0 and comma-separated candidates.
    if isinstance(current_value, bool):
        parsed: list[bool] = []
        for token in [p.strip().lower() for p in raw_values.split(",") if p.strip()]:
            if token in {"true", "1", "yes", "y"}:
                parsed.append(True)
            elif token in {"false", "0", "no", "n"}:
                parsed.append(False)
            else:
                raise ValueError(f"Invalid boolean token '{token}'")
        return parsed

    # Strings: comma-separated explicit values.
    if isinstance(current_value, str):
        values = [p.strip() for p in raw_values.split(",") if p.strip()]
        if not values:
            raise ValueError("No string values supplied")
        return values

    # Lists: allow either one comma-separated list, or multiple lists split by ';'.
    if isinstance(current_value, list):
        candidates: list[list[Any]] = []
        list_groups = [g.strip() for g in raw_values.split(";") if g.strip()]

        for group in list_groups:
            if group.startswith("["):
                parsed_group = json.loads(group)
                if not isinstance(parsed_group, list):
                    raise ValueError("List candidate must be a JSON list")
                candidates.append(parsed_group)
            else:
                tokens = [t.strip() for t in group.split(",") if t.strip()]
                parsed_items: list[Any] = []
                for token in tokens:
                    try:
                        parsed_items.append(float(token))
                    except ValueError:
                        parsed_items.append(token)
                candidates.append(parsed_items)

        if not candidates:
            raise ValueError("No list values supplied")
        return candidates

    raise TypeError(f"Unsupported parameter type: {type(current_value).__name__}")


def main():
    # Load command line arguments
    import argparse
    parser = argparse.ArgumentParser(description='Run lap time simulation with optional parameter sweeps. \n Example usage: python sweep.py mass 250,350 --steps 10 --output results.csv')
    parser.add_argument('param', type=str, help='Parameter name to sweep (e.g. "mass", "aero_cp", "gear_ratios")')
    parser.add_argument('values', type=str, help='Values for sweep. Numeric: "250,350" (+--steps) or explicit list. String: "A,B". List: "2.7,2.0,1.6,1.3,1.2" or "[...];[...]"')
    parser.add_argument('--steps', type=int, default=5, help='Number of steps in the parameter sweep (default: 5)')
    parser.add_argument('--output', type=str, default=DEFAULT_OUTPUT_PATH, help='Optional path to save results as CSV')
    args = parser.parse_args()

    # Import modules
    from track.track import load_track
    from vehicle.vehicle import create_vehicle
    from simulator.simulator import run_lap_time_simulation

    print(f"Running parameter sweep for {args.param} with values {args.values} and {args.steps} steps")


    # Load track data
    print("Using track file_path:", config["track"]["file_path"])
    try:
        track = load_track(config["track"]["file_path"], config.get("debug_mode", False))
        print(f"Loaded track with {len(track.points)} points, total length: {track.total_length:.2f} m")
    except Exception as e:
        print("Error loading track:", e)
        return # unix exit code for bad input

    # Load vehicle parameters
    try:
        vehicle = create_vehicle(config)
        print(f"Loaded vehicle: {vehicle.params.name}, mass: {vehicle.params.mass} kg")
    except Exception as e:
        print("Error loading vehicle:", e)
        return 65 # unix exit code for bad input
    
    alias_map = _build_param_alias_map()
    canonical_param = alias_map.get(args.param, args.param)

    if not hasattr(vehicle.params, canonical_param):
        print(f"Error: Vehicle has no parameter named {args.param} (resolved as {canonical_param})")
        return 22 # unix exit code for invalid argument

    # Initialise simulation loop
    try:
        current_value = getattr(vehicle.params, canonical_param)
        param_values = _coerce_values(args.values, current_value, args.steps)

        results = []
        for val in param_values:
            print(f"Running simulation with {canonical_param} = {val}")
            # Change the specified parameter in the vehicle
            if hasattr(vehicle.params, canonical_param):
                setattr(vehicle.params, canonical_param, val)
                print(f"Set vehicle parameter {canonical_param} to {val}")
            else:
                print(f"Warning: Vehicle has no parameter named {canonical_param}")
            sim_result = run_lap_time_simulation(track, vehicle, config, display=False)
            results.append((val, sim_result.lap_time))
        print("-----------------------")
        print("Parameter sweep results:")
        for val, lap_time in results:
            if isinstance(val, (int, float)):
                value_label = f"{val:.2f}"
            else:
                value_label = str(val)
            print(f"{canonical_param} = {value_label}, Lap Time = {lap_time:.2f} s")
        # print max and min lap times
        import numpy as np
        lap_times = [r[1] for r in results]
        print("-----------------------")
        best_val = results[np.argmin(lap_times)][0]
        worst_val = results[np.argmax(lap_times)][0]
        print(f"Best lap time: {min(lap_times):.2f} s at {canonical_param} = {best_val}")
        print(f"Worst lap time: {max(lap_times):.2f} s at {canonical_param} = {worst_val}")

        if args.output:
            os.makedirs(os.path.dirname(args.output), exist_ok=True)
            import csv
            with open(args.output, 'w', newline='') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow([canonical_param, 'Lap Time (s)'])
                for val, lap_time in results:
                    writer.writerow([val, lap_time])
            print("-----------------------")
            print(f"Results saved to {args.output}")

    except Exception as e:
        print("Error during simulation:", e)
        return 1 # unix exit code for error

if __name__ == "__main__":
    exit(main())