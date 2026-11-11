
import json

from vehicle.vehicle import create_vehicle
from simulator.util.transientDynamics import VehicleState, update_vehicle

# Load the existing LGR vehicle
with open("config.json") as file:
    config = json.load(file)

vehicle = create_vehicle(config)


# Initialise the vehicle at 60 km/h
state = VehicleState(longitudinal_velocity=60 / 3.6)

speed = 60 / 3.6
gear = vehicle.select_optimal_gear(speed)

rear_load = (
    vehicle.params.mass * 9.81
    * (1 - vehicle.params.cog_longitudinal_pos) / 2
)

max_fx_rear = (
    2 * abs(vehicle.tyre_model.get_longitudinal_force(12.0, rear_load))
    * vehicle.scenario_grip_scale
)

print(f"Rear tyre grip limit: {max_fx_rear:.1f} N")

for throttle in [0.5, 0.75, 1.0]:
    drive_force = (
        vehicle.compute_longitudinal_force(speed, gear, throttle)
        + vehicle.compute_aero_drag(speed)
    )
    print(f"Drive force for {throttle:.2f} throttle is {drive_force:.1f}")

delta_time = 0.01
simulation_time = 4.0
steering_angle = 0.0
yaw_inertia = 100.0

for i in range(int(simulation_time / delta_time)):
    time = i * delta_time

    # Accelerate for 2 seconds, brake for 1, then coast
    if time < 2.0:
        throttle = 0.75
        brake = 0.0
    elif time < 3.0:
        throttle = 0.0
        brake = 0.0
    else:
        throttle = 0.0
        brake = 0.0

    acceleration = update_vehicle(
        state,
        vehicle,
        steering_angle,
        throttle,
        brake,
        yaw_inertia,
        delta_time
    )

    if (i + 1) % 50 == 0:
        print(
            f"Time: {(i + 1) * delta_time:.1f}s | "
            f"Speed: {state.longitudinal_velocity * 3.6:.2f} km/h | "
            f"Yaw Rate: {state.yaw_rate:.4f} rad/s | "
            f"Lateral Velocity: {state.lateral_velocity:.4f} m/s"
        )
