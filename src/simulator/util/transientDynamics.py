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


def run_transient_replay(track, vehicle, speeds, yaw_inertia=100.0):

    # Initialise the vehicle at the circuit start
    state = VehicleState(
        longitudinal_velocity=float(speeds[0]),
        x=track.points[0].x,
        y=track.points[0].y,
        heading=track.points[0].heading
    )

    results = []

    delta_time = 0.01
    elapsed_time = 0.0

    distance = track.points[0].distance
    nearest_segment = 0
    point_index = 1

    steering = 0.0
    throttle = 0.0
    brake = 0.0

    # Run the simulation for up to 180 seconds
    for step in range(int(180 / delta_time)):

        if point_index >= len(track.points):
            break

        # Recalculate controls every 0.3 seconds
        if step % 30 == 0:
            steering, throttle, brake = calculate_predictive_controls(
                state,
                vehicle,
                track,
                nearest_segment,
                yaw_inertia
            )

        # Simulate the vehicle using the selected inputs
        update_vehicle(
            state,
            vehicle,
            steering,
            throttle,
            brake,
            yaw_inertia,
            delta_time
        )

        elapsed_time += delta_time

        # Stop if vehicle state becomes numerically unreliable
        if (
            not all(math.isfinite(v) for v in (
                state.longitudinal_velocity,
                state.lateral_velocity,
                state.yaw_rate,
                state.x,
                state.y,
                state.heading
            ))
            or abs(state.yaw_rate) > 5.0
            or abs(state.lateral_velocity) > 10.0
            or state.longitudinal_velocity < 0.5
        ):
            print(
                f"Replay stopped at {distance:.1f}m | "
                f"Forward Speed: {state.longitudinal_velocity:.2f}m/s | "
                f"Lateral Velocity: {state.lateral_velocity:.2f}m/s | "
                f"Yaw Rate: {state.yaw_rate:.2f}rad/s | "
                f"Throttle: {throttle:.2f} | "
                f"Brake: {brake:.2f}"
            )
            break

        # Determine actual progress along the racing line
        nearest_segment, measured_distance, path_error = project_to_track(
            state, track, nearest_segment
        )

        distance = max(distance, measured_distance)

        # Emergency path deviation check
        if path_error > 8.0:
            print(
                f"Replay stopped: vehicle is "
                f"{path_error:.1f}m from the path"
            )
            break

        # Record results whenever a track point is passed
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



def project_to_track(state, track, last_segment):
    """Find the nearest point on the reference racing line."""

    points = track.points
    last_segment = max(0, min(last_segment, len(points) - 2))

    start = max(0, last_segment - 5)
    end = min(len(points) - 1, last_segment + 25)

    best_error_sq = float("inf")
    best_segment = last_segment
    best_progress = points[last_segment].distance

    for i in range(start, end):
        p1 = points[i]
        p2 = points[i + 1]

        dx = p2.x - p1.x
        dy = p2.y - p1.y
        length_sq = dx * dx + dy * dy

        if length_sq < 1e-10:
            continue

        # Project vehicle position onto the track segment
        t = (
            (state.x - p1.x) * dx
            + (state.y - p1.y) * dy
        ) / length_sq

        t = max(0.0, min(1.0, t))

        closest_x = p1.x + t * dx
        closest_y = p1.y + t * dy

        error_sq = (
            (state.x - closest_x)**2
            + (state.y - closest_y)**2
        )

        if error_sq < best_error_sq:
            best_error_sq = error_sq
            best_segment = i
            best_progress = (
                p1.distance + t * (p2.distance - p1.distance)
            )

    return best_segment, best_progress, math.sqrt(best_error_sq)



def calculate_predictive_controls(state, vehicle, track,
                                  nearest_segment, yaw_inertia):

    # ==========================================
    # CONTROLLER SETTINGS
    # ==========================================

    prediction_time = 4.2       # Seconds to look into the future
    prediction_dt = 0.06        # Physics timestep during predictions
    control_interval = 0.30     # Must match real controller update interval
    steering_switch_time = 1.2 # When a strategy can change steering bias

    # Temporary racing-line corridor (not actual track boundaries)
    max_path_error = 3.0        # Metres
    max_sideslip = 15.0         # Degrees
    max_yaw_rate = 4.8          # rad/s

    wheelbase = vehicle.params.wheelbase
    points = track.points
    last_distance = points[-1].distance

    steps = int(round(prediction_time / prediction_dt))
    control_steps = max(1, int(round(control_interval / prediction_dt)))

    # ==========================================
    # GENERATE STEERING STRATEGIES
    # ==========================================

    # Initial adjustments to Pure Pursuit steering
    steering_strategies = [
        (offset, 0.0)
        for offset in (-12, -9, -6, -3, 0, 3, 6, 9, 12)
    ]

    # Additional strategies that change steering later
    steering_strategies += [
        (0, -6),
        (0, 6),
        (-6, 6),
        (6, -6)
    ]

    # Each tuple contains:
    # (initial steering offset, additional future offset)

    # ==========================================
    # GENERATE THROTTLE / BRAKE STRATEGIES
    # ==========================================

    # Each strategy contains:
    # (time, throttle, brake)

    plans = [
        [(0.0, 0.0, 0.0)],  # Coast
        [(0.0, 0.5, 0.0)],  # Half throttle
        [(0.0, 1.0, 0.0)],  # Full throttle
        [(0.0, 0.0, 0.5)],  # Half brake
        [(0.0, 0.0, 1.0)]   # Full brake
    ]

    # Accelerate now, then brake later
    for brake_start in (0.6, 1.2, 1.8, 2.4):
        for brake_level in (0.5, 1.0):
            plans.append([
                (0.0, 1.0, 0.0),
                (brake_start, 0.0, brake_level)
            ])

    # Partial throttle now, then brake later
    for brake_start in (0.9, 1.8):
        for brake_level in (0.5, 1.0):
            plans.append([
                (0.0, 0.5, 0.0),
                (brake_start, 0.0, brake_level)
            ])

    # Brake now, then accelerate later
    for brake_duration in (0.6, 1.2, 1.8):
        plans.append([
            (0.0, 0.0, 1.0),
            (brake_duration, 0.7, 0.0)
        ])

    # Coast now, then brake later
    for brake_start in (1.2, 2.4):
        plans.append([
            (0.0, 0.0, 0.0),
            (brake_start, 0.0, 1.0)
        ])

    # ==========================================
    # REFERENCE STEERING
    # ==========================================

    def pure_pursuit(predicted, segment, progress):

        lookahead = max(
            4.0,
            min(12.0, predicted.longitudinal_velocity * 0.45)
        )

        target_distance = min(
            last_distance,
            progress + lookahead
        )

        i = min(segment + 1, len(points) - 1)

        while (
            i < len(points) - 1
            and points[i].distance < target_distance
        ):
            i += 1

        p1 = points[i - 1]
        p2 = points[i]

        fraction = (
            (target_distance - p1.distance)
            / max(1e-9, p2.distance - p1.distance)
        )
        fraction = max(0.0, min(1.0, fraction))

        target_x = p1.x + fraction * (p2.x - p1.x)
        target_y = p1.y + fraction * (p2.y - p1.y)

        dx = target_x - predicted.x
        dy = target_y - predicted.y

        angle_error = (
            math.atan2(dy, dx) - predicted.heading
        )

        return math.degrees(math.atan2(
            2.0 * wheelbase * math.sin(angle_error),
            max(1e-6, math.hypot(dx, dy))
        ))

    # ==========================================
    # INITIALISE SEARCH
    # ==========================================

    start_segment, start_progress, initial_error = project_to_track(
        state, track, nearest_segment
    )

    if initial_error > max_path_error:
        raise RuntimeError(
            f"Vehicle already {initial_error:.1f}m from racing line"
        )

    best_score = -float("inf")
    best_action = None

    # ==========================================
    # SIMULATE COMPLETE DRIVING STRATEGIES
    # ==========================================

    for early_offset, later_change in steering_strategies:
        for plan in plans:

            # Copy vehicle state for this strategy
            predicted = replace(state)
            segment = start_segment
            progress = start_progress

            score_penalty = 0.0
            plan_index = 0

            steering = 0.0
            first_action = None
            feasible = True

            # Simulate the entire prediction horizon
            for step in range(steps):

                t = step * prediction_dt

                # Select throttle/brake for this future time
                while (
                    plan_index + 1 < len(plan)
                    and t >= plan[plan_index + 1][0] - 1e-9
                ):
                    plan_index += 1

                _, throttle, brake = plan[plan_index]

                # Recalculate steering at the same frequency
                # as the real controller
                if step % control_steps == 0:

                    base_steering = pure_pursuit(
                        predicted, segment, progress
                    )

                    offset = early_offset

                    if t >= steering_switch_time:
                        offset += later_change

                    steering = max(
                        -20.0,
                        min(20.0, base_steering + offset)
                    )

                # Save the first action to apply to real car
                if first_action is None:
                    first_action = (steering, throttle, brake)

                # Simulate vehicle physics
                update_vehicle(
                    predicted,
                    vehicle,
                    steering,
                    throttle,
                    brake,
                    yaw_inertia,
                    prediction_dt
                )

                # Check numerical validity
                values = (
                    predicted.x,
                    predicted.y,
                    predicted.heading,
                    predicted.longitudinal_velocity,
                    predicted.lateral_velocity,
                    predicted.yaw_rate
                )

                if not all(math.isfinite(v) for v in values):
                    feasible = False
                    break

                # Determine position relative to racing line
                segment, projected_progress, path_error = project_to_track(
                    predicted, track, segment
                )

                sideslip = math.degrees(math.atan2(
                    predicted.lateral_velocity,
                    max(0.5, predicted.longitudinal_velocity)
                ))

                # ==================================
                # HARD SAFETY CONSTRAINTS
                # ==================================

                if (
                    path_error > max_path_error
                    or abs(sideslip) > max_sideslip
                    or abs(predicted.yaw_rate) > max_yaw_rate
                    or abs(predicted.lateral_velocity) > 9.5
                    or predicted.longitudinal_velocity < 0.5
                ):
                    feasible = False
                    break

                # Estimate progress, avoiding large jumps
                # caused by track projection
                actual_speed = math.hypot(
                    predicted.longitudinal_velocity,
                    predicted.lateral_velocity
                )

                max_ds = (
                    actual_speed * prediction_dt * 1.25 + 0.15
                )

                progress = max(
                    progress,
                    min(projected_progress, progress + max_ds)
                )

                # ==================================
                # SCORE PATH QUALITY
                # ==================================

                # Staying within the corridor is mandatory.
                # Inside it, prefer smaller path errors
                # and less sideslip.
                score_penalty += prediction_dt * (
                    2.0 * path_error**2
                    + 0.02 * sideslip**2
                )

                # Reached the end of the circuit
                if progress >= last_distance - 0.1:
                    break

            # Only evaluate trajectories that remained feasible
            if not feasible:
                continue

            # Reward progress, penalise poor path following
            score = (
                progress - start_progress
                - score_penalty
            )

            if score > best_score:
                best_score = score
                best_action = first_action

    # ==========================================
    # RETURN BEST STRATEGY
    # ==========================================

    if best_action is None:
        raise RuntimeError(
            f"No feasible {prediction_time:.1f}s strategy at "
            f"{start_progress:.1f}m | "
            f"Speed: {state.longitudinal_velocity * 3.6:.1f}km/h"
        )

    return best_action
