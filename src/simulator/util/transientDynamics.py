from dataclasses import dataclass, replace
import math

@dataclass
class VehicleState:
    longitudinal_velocity: float = 0.0
    lateral_velocity: float = 0.0
    yaw_rate: float = 0.0

    x: float = 0.0
    y: float = 0.0
    heading: float = 0.0


def update_state(state, vehicle, forward_speed, steering_angle, yaw_inertia, delta_time):
    # Distance from centre of gravity to each axel
    lr = vehicle.params.wheelbase * vehicle.params.cog_longitudinal_pos
    lf = vehicle.params.wheelbase - lr

    # Convert steering angle from degrees to radians
    steer = math.radians(steering_angle)

    # Calculate tyre slip angles
    front_slip = steer - math.atan2(state.lateral_velocity + lf * state.yaw_rate, forward_speed)
    rear_slip = -math.atan2(state.lateral_velocity - lr * state.yaw_rate, forward_speed)

    # Calculate lateral forces at the front and rear axels
    front_force, rear_force = vehicle.compute_tyre_forces(math.degrees(front_slip), math.degrees(rear_slip))

    # Resolve front lateral force into the vehicle's lateral direction
    front_lateral = front_force * math.cos(steer)

    # Calculate lateral velocity acceleration
    lateral_acceleration = ((front_lateral + rear_force) / vehicle.params.mass - forward_speed * state.yaw_rate)

    # Calculate yaw acceleration
    yaw_acceleration = (lf * front_lateral - lr * rear_force) / yaw_inertia

    # Calculate velocity in world coordinates
    velocity_x = (forward_speed * math.cos(state.heading)- state.lateral_velocity * math.sin(state.heading))
    velocity_y = (forward_speed * math.sin(state.heading) + state.lateral_velocity * math.cos(state.heading))

    # Update vehicle position and heading
    state.x += velocity_x * delta_time
    state.y += velocity_y * delta_time
    state.heading += state.yaw_rate * delta_time

    # Update lateral velocity and yaw rate
    state.lateral_velocity += lateral_acceleration * delta_time
    state.yaw_rate += yaw_acceleration * delta_time



def update_longitudinal_speed(state, vehicle, throttle, brake, delta_time):
    # Clamp inputs between 0 and 1
    throttle = max(0.0, min(1.0, throttle))
    brake = max(0.0, min(1.0, brake))

    speed = state.longitudinal_velocity

    # If the vehicle is stationary and not accelerating, keep it stationary
    if speed <= 0.0 and throttle <= 0.0:
        state.longitudinal_velocity = 0.0
        return 0.0

    # Calculate aerodynamic drag
    drag_force = vehicle.compute_aero_drag(speed)

    # Calculate longitudinal tyre grip limits
    normal_load = vehicle.compute_static_normal_load()

    drive_grip_limit = 2 * abs(vehicle.tyre_model.get_longitudinal_force(12.0, normal_load)) * vehicle.scenario_grip_scale

    brake_grip_limit = 4 * abs(vehicle.tyre_model.get_longitudinal_force(-12.0, normal_load)) * vehicle.scenario_grip_scale

    # Calculate driving force using the existing powertrain
    drive_force = 0.0

    if throttle > 0:
        gear = vehicle.select_optimal_gear(max(speed, 1.0))

        # Existing function includes aerodynamic drag,
        # so add it back to obtain driving force alone
        drive_force = vehicle.compute_longitudinal_force(max(speed, 1.0), gear, throttle) + vehicle.compute_aero_drag(max(speed, 1.0))

        drive_force = min(max(0.0, drive_force), drive_grip_limit)

    # Braking force, limited by tyre grip
    brake_force = brake * brake_grip_limit

    # Calculate net longitudinal force and acceleration
    net_force = drive_force - brake_force - drag_force
    acceleration = net_force / vehicle.params.mass

    # Update forward velocity
    new_speed = speed + acceleration * delta_time

    if new_speed < 0.0:
        # Vehicle stops during this timestep
        acceleration = -speed / delta_time
        new_speed = 0.0

    state.longitudinal_velocity = new_speed

    return acceleration




def run_transient_replay(track, vehicle, speeds, yaw_inertia=100.0): # TODO: Get realistic yaw inertia value
    # Initialise the car at the beginning of the circuit
    state = VehicleState(
        longitudinal_velocity=float(speeds[0]),
        x=track.points[0].x,
        y=track.points[0].y,
        heading=track.points[0].heading
    )

    results = []
    delta_time = 0.01
    elapsed_time = 0.0
    predicted_throttle = 0.0
    predicted_brake = 0.0

    # Distance progressed along the reference circuit
    distance = track.points[0].distance
    point_index = 1
    nearest_segment = 0

    # Run for at most 180 simulated seconds
    for step in range(int(180 / delta_time)):
        if point_index >= len(track.points):
            break

        previous = track.points[point_index - 1]
        current = track.points[point_index]

        ds = current.distance - previous.distance

        if ds <= 0:
            point_index += 1
            continue
        
        # Calculate steering based on the car's actual position
        steering, nearest_segment, measured_distance, path_error = calculate_steering(
            state, track, nearest_segment, vehicle.params.wheelbase
        )

        # Track progress now comes from the vehicle's actual position
        distance = max(distance, measured_distance)

        # Stop if the car moves too far from the intended path
        if path_error > 8.0:
            print(f"Replay stopped: vehicle is {path_error:.1f}m from the path")
            break

        # Interpolate the target speed at the current track position
        fraction = max(0.0, min(
            1.0, (distance - previous.distance) / ds
        ))

        # Interpolate target speed from the QSS profile
        target_speed = (
            speeds[point_index - 1]
            + (speeds[point_index] - speeds[point_index - 1]) * fraction
        )

        
        # Recalculate predictive inputs every 0.2 seconds
        if step % 20 == 0:

            # First decide whether braking is needed
            predicted_brake = calculate_predictive_brake(
                state,
                vehicle,
                track,
                speeds,
                nearest_segment,
                yaw_inertia
            )

            # Only evaluate throttle if we don't need to brake
            if predicted_brake < 0.05:
                predicted_throttle = calculate_predictive_throttle(
                    state,
                    vehicle,
                    track,
                    speeds,
                    nearest_segment,
                    yaw_inertia
                )
            else:
                predicted_throttle = 0.0

        # Apply the selected inputs
        if predicted_brake >= 0.05:
            throttle = 0.0
            brake = predicted_brake
        else:
            throttle = predicted_throttle
            brake = 0.0


        # Update the transient vehicle model
        update_vehicle(
            state, vehicle, steering, throttle, brake,
            yaw_inertia, delta_time
        )

        elapsed_time += delta_time

        # Stop if the simplified model becomes unreliable
        if (
            not all(math.isfinite(v) for v in (
                state.longitudinal_velocity,
                state.lateral_velocity,
                state.yaw_rate,
                state.x,
                state.y
            ))
            or state.longitudinal_velocity < 0.5
            or abs(state.lateral_velocity) > 10.0
            or abs(state.yaw_rate) > 5.0
        ):
            print(f"Replay stopped near {distance:.1f}m: unstable state")
            break

        # Record results whenever another track point is passed
        while (
            point_index < len(track.points)
            and distance >= track.points[point_index].distance
        ):
            point = track.points[point_index]

            results.append((
                point.distance,
                state.yaw_rate,
                state.longitudinal_velocity * point.curvature,
                state.x,
                state.y,
                state.longitudinal_velocity,
                float(speeds[point_index]),
                elapsed_time,
                throttle,
                brake,
                path_error
            ))

            point_index += 1

    else:
        print("Replay stopped: maximum simulation time reached")

    return results



def update_vehicle(state, vehicle, steering_angle, throttle, brake,
                   yaw_inertia, delta_time):

    throttle = max(0.0, min(1.0, throttle))
    brake = max(0.0, min(1.0, brake))

    mass = vehicle.params.mass
    speed = state.longitudinal_velocity
    lateral_speed = state.lateral_velocity
    yaw_rate = state.yaw_rate
    steer = math.radians(steering_angle)

    # Distance from centre of gravity to each axle
    lr = vehicle.params.wheelbase * vehicle.params.cog_longitudinal_pos
    lf = vehicle.params.wheelbase - lr

    # Calculate front and rear tyre slip angles
    front_slip = steer - math.atan2(
        lateral_speed + lf * yaw_rate, max(speed, 0.1)
    )
    rear_slip = -math.atan2(
        lateral_speed - lr * yaw_rate, max(speed, 0.1)
    )

    # Static normal load per tyre
    front_load = mass * 9.81 * vehicle.params.cog_longitudinal_pos / 2
    rear_load = mass * 9.81 * (1 - vehicle.params.cog_longitudinal_pos) / 2

    # Calculate requested lateral forces at each axle
    fy_front, fy_rear = vehicle.compute_tyre_forces(
        math.degrees(front_slip),
        math.degrees(rear_slip),
        front_load,
        rear_load
    )

    tyre = vehicle.tyre_model
    grip_scale = vehicle.scenario_grip_scale

    # Approximate longitudinal grip limits per axle
    max_fx_front = 2 * abs(tyre.get_longitudinal_force(
        12.0, front_load)) * grip_scale

    max_fx_rear = 2 * abs(tyre.get_longitudinal_force(
        12.0, rear_load)) * grip_scale

    # Estimate peak lateral forces by sampling tyre slip angles
    sample_angles = (4.0, 8.0, 12.0, 16.0)

    max_fy_front = 2 * max(
        abs(tyre.get_lateral_force(a, front_load))
        for a in sample_angles
    ) * grip_scale

    max_fy_rear = 2 * max(
        abs(tyre.get_lateral_force(a, rear_load))
        for a in sample_angles
    ) * grip_scale

    # Calculate driving force (assume rear-wheel drive)
    drive_force = 0.0

    if throttle > 0:
        engine_speed = max(speed, 1.0)
        gear = vehicle.select_optimal_gear(engine_speed)

        drive_force = max(0.0,
            vehicle.compute_longitudinal_force(
                engine_speed, gear, throttle
            ) + vehicle.compute_aero_drag(engine_speed)
        )

    # Requested longitudinal forces
    # Braking is distributed according to axle grip capacity
    fx_front = -brake * max_fx_front
    fx_rear = drive_force - brake * max_fx_rear

    # Apply combined grip limits at each axle
    fx_front, fy_front = limit_combined_forces(
        fx_front, fy_front, max_fx_front, max_fy_front
    )

    fx_rear, fy_rear = limit_combined_forces(
        fx_rear, fy_rear, max_fx_rear, max_fy_rear
    )

    # Resolve front tyre forces into vehicle coordinates
    front_force_x = fx_front * math.cos(steer) - fy_front * math.sin(steer)
    front_force_y = fx_front * math.sin(steer) + fy_front * math.cos(steer)

    # Calculate vehicle accelerations
    drag = vehicle.compute_aero_drag(speed)

    longitudinal_acceleration = (
        (front_force_x + fx_rear - drag) / mass
        + yaw_rate * lateral_speed
    )

    lateral_acceleration = (
        (front_force_y + fy_rear) / mass
        - yaw_rate * speed
    )

    yaw_acceleration = (
        lf * front_force_y - lr * fy_rear
    ) / yaw_inertia

    # Calculate velocity in world coordinates
    velocity_x = (
        speed * math.cos(state.heading)
        - lateral_speed * math.sin(state.heading)
    )

    velocity_y = (
        speed * math.sin(state.heading)
        + lateral_speed * math.cos(state.heading)
    )

    # Update position and heading
    state.x += velocity_x * delta_time
    state.y += velocity_y * delta_time
    state.heading += yaw_rate * delta_time

    # Update vehicle velocities
    new_speed = max(0.0, speed + longitudinal_acceleration * delta_time)

    state.longitudinal_velocity = new_speed
    state.lateral_velocity += lateral_acceleration * delta_time
    state.yaw_rate += yaw_acceleration * delta_time

    # Return actual longitudinal acceleration
    return (new_speed - speed) / delta_time




def limit_combined_forces(fx, fy, max_fx, max_fy):
    # Calculate how much of the available grip is being requested
    utilisation = math.hypot(
        fx / max(max_fx, 1e-6),
        fy / max(max_fy, 1e-6)
    )

    # Reduce both forces if the tyre grip limit is exceeded
    if utilisation > 1.0:
        fx /= utilisation
        fy /= utilisation

    return fx, fy


def calculate_steering(state, track, last_segment, wheelbase):
    points = track.points

    # Search nearby track segments for the car's position
    start = max(0, last_segment - 3)
    end = min(len(points) - 1, last_segment + 20)

    best_distance = float("inf")
    nearest_segment = last_segment
    track_distance = 0.0

    for i in range(start, end):
        p1 = points[i]
        p2 = points[i + 1]

        dx = p2.x - p1.x
        dy = p2.y - p1.y
        length_sq = dx * dx + dy * dy

        if length_sq < 1e-10:
            continue

        # Project the vehicle position onto the track segment
        t = ((state.x - p1.x) * dx + (state.y - p1.y) * dy) / length_sq
        t = max(0.0, min(1.0, t))

        closest_x = p1.x + t * dx
        closest_y = p1.y + t * dy

        distance_sq = (
            (state.x - closest_x) ** 2
            + (state.y - closest_y) ** 2
        )

        if distance_sq < best_distance:
            best_distance = distance_sq
            nearest_segment = i
            track_distance = p1.distance + t * (p2.distance - p1.distance)

    # Choose a target point ahead of the car
    lookahead = max(8.0, min(18.0, state.longitudinal_velocity * 0.7))
    target_distance = min(points[-1].distance, track_distance + lookahead)

    target_index = nearest_segment + 1

    while (target_index < len(points) - 1
           and points[target_index].distance < target_distance):
        target_index += 1

    p1 = points[target_index - 1]
    p2 = points[target_index]

    # Interpolate target position
    segment_length = max(p2.distance - p1.distance, 1e-6)
    t = (target_distance - p1.distance) / segment_length

    target_x = p1.x + t * (p2.x - p1.x)
    target_y = p1.y + t * (p2.y - p1.y)

    # Calculate direction from car to target
    dx = target_x - state.x
    dy = target_y - state.y

    target_angle = math.atan2(dy, dx)
    angle_error = target_angle - state.heading

    distance_to_target = max(math.hypot(dx, dy), 1e-6)

    # Pure Pursuit steering calculation
    steering = math.atan2(
        2 * wheelbase * math.sin(angle_error),
        distance_to_target
    )

    steering_degrees = math.degrees(steering)
    steering_degrees = max(-20.0, min(20.0, steering_degrees))

    return steering_degrees, nearest_segment, track_distance, math.sqrt(best_distance)



def calculate_speed_inputs(state, track, speeds, distance, point_index, target_speed):
    speed = state.longitudinal_velocity

    # Controller settings
    lookahead_distance = 100.0
    estimated_braking = 7.0  # m/s²
    max_brake = 0.7
    max_throttle = 0.5

    # Start with the current target speed
    allowed_speed = float(target_speed)

    # Check upcoming corners
    for i in range(point_index, len(track.points)):
        ds = track.points[i].distance - distance

        if ds > lookahead_distance:
            break

        if ds <= 0:
            continue

        upcoming_speed = float(speeds[i])

        # Maximum speed we can travel now while still
        # being able to brake to the upcoming speed
        max_speed_now = math.sqrt(
            upcoming_speed**2 + 2.0 * estimated_braking * ds
        )

        allowed_speed = min(allowed_speed, max_speed_now)

    # Compare actual speed against allowable speed
    speed_error = allowed_speed - speed

    if speed_error < 0:
        # Vehicle is travelling too quickly
        throttle = 0.0
        brake = min(max_brake, -speed_error * 0.2)
    else:
        # Vehicle can accelerate towards target
        throttle = min(max_throttle, speed_error * 0.15)
        brake = 0.0

    return throttle, brake


def calculate_predictive_throttle(state, vehicle, track, speeds,
                                  nearest_segment, yaw_inertia):

    # Throttle inputs to test
    throttle_options = [0.0, 0.15, 0.30, 0.45, 0.60, 0.75, 0.90, 1.0]

    # Prediction settings
    prediction_time = 0.7
    delta_time = 0.02
    steps = int(prediction_time / delta_time)

    best_throttle = 0.0

    for throttle in throttle_options:

        # Copy the current state so predictions don't
        # affect the real simulation
        predicted_state = replace(state)
        predicted_segment = nearest_segment
        safe = True

        for _ in range(steps):

            # Calculate steering for the predicted position
            steering, predicted_segment, distance, path_error = calculate_steering(
                predicted_state,
                track,
                predicted_segment,
                vehicle.params.wheelbase
            )

            # Simulate the vehicle with this throttle input
            update_vehicle(
                predicted_state,
                vehicle,
                steering,
                throttle,
                0.0,
                yaw_inertia,
                delta_time
            )

            # Calculate the predicted sideslip angle
            sideslip = math.degrees(math.atan2(
                predicted_state.lateral_velocity,
                max(predicted_state.longitudinal_velocity, 0.1)
            ))

            # Reject unstable predictions
            if (
                not all(math.isfinite(v) for v in (
                    predicted_state.x,
                    predicted_state.y,
                    predicted_state.longitudinal_velocity,
                    predicted_state.lateral_velocity,
                    predicted_state.yaw_rate
                ))
                or abs(sideslip) > 10.0
                or abs(predicted_state.yaw_rate) > 4.0
                or path_error > 6.0
                or predicted_state.longitudinal_velocity < 0.5
            ):
                safe = False
                break

            # Interpolate the QSS speed target at the
            # predicted position along the track
            p1 = track.points[predicted_segment]
            p2 = track.points[predicted_segment + 1]

            ds = max(p2.distance - p1.distance, 1e-6)
            fraction = max(0.0, min(
                1.0, (distance - p1.distance) / ds
            ))

            target_speed = (
                float(speeds[predicted_segment]) * (1 - fraction)
                + float(speeds[predicted_segment + 1]) * fraction
            )

            # Don't accelerate significantly beyond the
            # speed profile's predicted limit
            if predicted_state.longitudinal_velocity > target_speed + 1.0:
                safe = False
                break

        # Options are in increasing throttle order,
        # so the last safe option is the highest
        if safe:
            best_throttle = throttle

    return best_throttle



def calculate_predictive_brake(state, vehicle, track, speeds,
                               nearest_segment, yaw_inertia):

    brake_options = [0.0, 0.15, 0.30, 0.45, 0.60, 0.80, 1.0]

    prediction_time = 1.2
    delta_time = 0.02
    steps = int(prediction_time / delta_time)

    best_brake = 0.0
    best_score = float("inf")

    for brake in brake_options:
        predicted_state = replace(state)
        predicted_segment = nearest_segment
        score = 0.0

        for _ in range(steps):
            # Find the predicted position and steering
            steering, predicted_segment, distance, path_error = calculate_steering(
                predicted_state,
                track,
                predicted_segment,
                vehicle.params.wheelbase
            )

            # Simulate with this braking input
            update_vehicle(
                predicted_state, vehicle, steering,
                0.0, brake, yaw_inertia, delta_time
            )

            # Reject numerically unstable predictions
            if not all(math.isfinite(v) for v in (
                predicted_state.x,
                predicted_state.y,
                predicted_state.longitudinal_velocity,
                predicted_state.lateral_velocity,
                predicted_state.yaw_rate
            )):
                score = float("inf")
                break

            # Find the QSS target speed at the predicted position
            p1 = track.points[predicted_segment]
            p2 = track.points[predicted_segment + 1]

            ds = max(p2.distance - p1.distance, 1e-6)
            fraction = max(0.0, min(
                1.0, (distance - p1.distance) / ds
            ))

            target_speed = (
                float(speeds[predicted_segment]) * (1 - fraction)
                + float(speeds[predicted_segment + 1]) * fraction
            )

            # Compare predicted speed with target speed
            speed_error = predicted_state.longitudinal_velocity - target_speed

            # Penalise exceeding the target speed more heavily
            overspeed = max(0.0, speed_error - 0.25)
            underspeed = max(0.0, -speed_error - 0.25)

            score += 6.0 * overspeed**2
            score += 3.0 * underspeed**2

            # Penalise large deviations from the racing line
            score += 2.0 * max(0.0, path_error - 4.0)**2

            # Penalise excessive sideslip
            sideslip = math.degrees(math.atan2(
                predicted_state.lateral_velocity,
                max(predicted_state.longitudinal_velocity, 0.1)
            ))

            score += 2.0 * max(0.0, abs(sideslip) - 8.0)**2

            # Avoid unreliable near-zero forward-speed behaviour
            if predicted_state.longitudinal_velocity < 0.5:
                score = float("inf")
                break

        # Slight preference for less braking when results are similar
        score += 0.1 * brake**2

        if score < best_score:
            best_score = score
            best_brake = brake

    return best_brake
