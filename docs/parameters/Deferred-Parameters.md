# Deferred Parameters (Production v1 Scope)

Purpose: declare which loaded parameters are intentionally deferred for production v1 and must not be used for active setup/tuning decisions.

## Deferred List

1. suspension_stiffness
2. damping_coefficient

## Why These Are Deferred

Current simulation architecture is quasi-static at the vehicle dynamics level. The two deferred parameters are primarily transient-response parameters.

- suspension_stiffness is most meaningful when heave/roll dynamics are explicitly modeled over time.
- damping_coefficient is most meaningful when velocity-dependent suspension transients are modeled over time.

In the current solver, wiring these parameters directly would risk pseudo-physics and false confidence rather than reliable engineering signal.

## Production Decision

For production v1:

1. Keep both parameters loaded for schema compatibility.
2. Mark both as deferred in parameter-enforcement audit status.
3. Exclude both from active setup/tuning recommendations.
4. Prioritize only parameters with direct first-principles enforcement and passing contracts.

## What Engineers Should Do Today

Use these as active tuning parameters:

- mass
- base_mu
- frontal_area
- drag_coefficient
- downforce_coefficient
- aero_cp
- wheelbase
- front_track_width
- rear_track_width
- cog_z
- cog_longitudinal_pos
- max_cog_z
- roll_stiffness
- max_roll_angle_deg
- wheel_radius
- final_drive_ratio
- gear_ratios
- transmission_efficiency

Do not use these for setup decisions yet:

- suspension_stiffness
- damping_coefficient

## Exit Criteria To Undefer

Undefer only when all are true:

1. A transient-capable suspension/vehicle dynamics layer exists.
2. Parameters are connected to runtime equations with unit-consistent terms.
3. Directional/monotonic contracts pass for both parameters.
4. Strict baseline and non-baseline gates pass without regressions.
