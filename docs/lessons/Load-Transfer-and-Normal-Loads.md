# Load Transfer and Normal Loads

## Read this after
Read [Aerodynamics Model Intro](Aero-Model.md) first.

## Goal
Explain how the simulator computes normal load, why normal load changes tyre force capacity, and which diagnostics show whether the load model is being stressed.

## One minute mental model
Tyres make force against the road, so the vertical load on each tyre matters.
More normal load usually gives more absolute tyre force, but not unlimited force and not always with constant friction coefficient.

The simulator tracks this at axle level.
It estimates front and rear normal load per tyre, then uses those loads when querying tyre force limits.

## Static normal load
If the car is stationary on level ground, total vertical load is approximately

$$
F_z = m g
$$

The front and rear axle shares come from the longitudinal centre of gravity location.
In code this is represented by `cog_longitudinal_pos`.

Conceptually

$$
F_{z,front,static} = m g \lambda_f
$$

$$
F_{z,rear,static} = m g (1 - \lambda_f)
$$

where $\lambda_f$ is the static front load fraction.
Per tyre values are axle loads divided by two.

`cog_longitudinal_pos` in `parameters.json` is the fraction of total mass carried by the front axle in static conditions.
A value of 0.5 means equal front and rear split.
A value of 0.516 means the front axle carries 51.6 percent of the car weight at rest.

## Aero load split
Downforce adds vertical load as speed rises.
The simulator computes total downforce and splits it across front and rear axles using aero centre of pressure.

If the aero centre of pressure moves rearward, more downforce goes to the rear tyres.
That can change cornering and traction balance even when total downforce is unchanged.

Code path

- [src/simulator/util/calcSpeedProfile.py](../../src/simulator/util/calcSpeedProfile.py) `_split_aero_load_by_cp`
- [src/vehicle/vehicle.py](../../src/vehicle/vehicle.py) `compute_downforce`
- [docs/parameters/Aero-CoP-Deep-Dive.md](../parameters/Aero-CoP-Deep-Dive.md)

## Longitudinal load transfer
When the car accelerates or brakes, inertia creates a pitch moment around the contact patches.
The simulator uses the quasi-static load transfer approximation

$$
\Delta F_z = \frac{m a_x h}{L}
$$

where

- $m$ is mass
- $a_x$ is longitudinal acceleration
- $h$ is centre of gravity height
- $L$ is wheelbase

Positive acceleration shifts load rearward.
Braking shifts load forward.

Code path

- [src/simulator/util/calcSpeedProfile.py](../../src/simulator/util/calcSpeedProfile.py) `_compute_normal_loads_for_longitudinal`

## How loads feed the tyre model
The tyre model receives front and rear normal loads when the solver asks for lateral or longitudinal force.

This matters because tyre force limits are load dependent.
Changing normal load changes available force in the corner solve, forward acceleration pass, and backward braking pass.

Runtime users

- Corner limit via `optimise_speed_at_points`
- Forward pass via `forward_pass`
- Backward pass via `backward_pass`

## Physical guardrails
The load model should not produce negative axle loads.
The implementation bounds transferable load so that each axle retains a small positive load in extreme cases.

The diagnostics report two types of events.

`normal_load_non_physical_events_total` is a red flag. A raw load became invalid or negative.
`normal_load_transfer_clamped_events_total` is a warning. The transfer calculation reached a guardrail.

Non-physical events should be zero for credible runs.
Clamp events can occur, but high counts mean the model is operating near its simplified assumptions.

## Rollover speed cap
The corner speed search also applies a quasi-static rollover speed cap.
The cap uses track width, centre of gravity height, gravity, and curvature radius.

$$
v_{roll} = \sqrt{\frac{t}{2h} g R}
$$

where

- $t$ is track width,
- $h$ is centre of gravity height,
- $g$ is gravitational acceleration,
- $R = 1 / |\kappa|$ is curvature radius.

A wider track raises the speed cap.
A higher centre of gravity lowers the speed cap.
A tighter curvature radius lowers the speed cap.

This is conservative because it is a compact quasi-static bound.
It does not model full suspension transient roll dynamics or tyre lift progression.

Code path

- [src/simulator/util/vehicleDynamics.py](../../src/simulator/util/vehicleDynamics.py) `v_rollover = sqrt((t / (2 * h)) * g * R)`
- [src/simulator/util/calcSpeedProfile.py](../../src/simulator/util/calcSpeedProfile.py) `_compute_rollover_speed_cap`

## Diagnostics to inspect
Useful channels include

- `corner_front_normal_load_per_tyre`
- `corner_rear_normal_load_per_tyre`
- `forward_front_normal_load_per_tyre`
- `forward_rear_normal_load_per_tyre`
- `backward_front_normal_load_per_tyre`
- `backward_rear_normal_load_per_tyre`
- `normal_load_non_physical_events_total`
- `normal_load_transfer_clamped_events_total`
- `corner_physical_cap_speed`

These channels are returned from [src/simulator/util/calcSpeedProfile.py](../../src/simulator/util/calcSpeedProfile.py) and summarized by A/B reports.

## Assumptions and limits
- Load transfer is quasi-static.
- The core solver does not model full suspension transient states.
- Lateral load transfer is represented through compact bounds and rollover checks rather than a full four-wheel suspension model.
- Aero load split uses a centre of pressure parameter rather than a full aero map.
- Transfer clamps protect the solver, but they are also a sign that assumptions should be checked.

## Verification checks
Relevant checks live in

- [tests/test_limiting_case_contracts.py](../../tests/test_limiting_case_contracts.py)
- [tests/test_solver_contracts.py](../../tests/test_solver_contracts.py)
- [src/ab_testing/run_ab_suite.py](../../src/ab_testing/run_ab_suite.py)

Milestone 3 gates require zero non-physical normal-load events and sensible sensitivity signs.

## Next lesson
- [Braking Dynamics and Deceleration Budget](Braking-Dynamics-and-Deceleration-Budget.md)

## Related lessons
- [Aerodynamics Model Intro](Aero-Model.md)
- [Tyre Model Deep Dive](Tyre-Model-Deep-Dive.md)
- [Vehicle Modelling Capstone](Vehicle-Modelling.md)
- [Vehicle Modelling Diagnostics and Trust Checks](Vehicle-Modelling-Diagnostics.md)
- [Validation and Falsification Workflow](Validation-and-Falsification-Workflow.md)
- [Lessons Index](README.md)
