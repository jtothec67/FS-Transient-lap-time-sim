# Braking Dynamics and Deceleration Budget

## Read this after
Read [Load Transfer and Normal Loads](Load-Transfer-and-Normal-Loads.md) first.

## Goal
Explain why braking is solved backwards, how tyre grip and lateral demand share the deceleration budget, and how to inspect braking-limited results.

## One minute mental model
A car must slow down early enough to make the next slower point.
That is why the braking pass starts at the end of the track point list and walks backwards.

The deceleration budget is the amount of braking authority still available after lateral cornering demand has used part of the tyre force envelope.

At each step, the solver asks four questions.

- How fast can the next point be.
- How much distance is available.
- How much deceleration can the tyres and drag provide.
- What is the fastest previous speed that can still brake down in time.

## Backward speed propagation
The backward pass uses constant-acceleration kinematics over each segment.

$$
v_i = \sqrt{v_{i+1}^2 + 2 a_{brake} \Delta s}
$$

Then it applies the corner speed ceiling.

$$
v_{pass3,i} = \min(v_{corner,i}, v_i)
$$

Code path

- [src/simulator/util/calcSpeedProfile.py](../../src/simulator/util/calcSpeedProfile.py) `backward_pass`

## Tyre braking force limit
The tyre model provides a longitudinal force cap from normal load and slip ratio.
The braking pass evaluates front and rear loads, then combines the axle force capacity.

Inputs include

- front and rear normal load per tyre,
- configured braking peak slip ratio,
- base tyre grip scale,
- current speed and curvature.

## Lateral demand consumes braking budget
If the car is cornering, the tyres are already spending part of their force capacity laterally.
This is the core deceleration budget check in the backward pass.

Lateral demand is estimated as

$$
F_y = m v^2 |\kappa|
$$

The solver computes a longitudinal budget scale from lateral demand and lateral tyre capacity.
When lateral demand is small, the scale is near 1.
When the car is close to lateral saturation, the scale approaches 0.

Conceptually

$$
F_{x,available} = F_{x,cap} \cdot \sqrt{1 - \left(\frac{F_y}{F_{y,cap}}\right)^2}
$$

This is a friction-circle or friction-ellipse style approximation.

Code path

- [src/simulator/util/calcSpeedProfile.py](../../src/simulator/util/calcSpeedProfile.py) `_longitudinal_budget_scale_from_lateral_demand`
- [src/simulator/util/calcSpeedProfile.py](../../src/simulator/util/calcSpeedProfile.py) `_compute_total_force_caps`

## Aero drag helps braking
Aerodynamic drag acts opposite vehicle motion.
During braking it adds deceleration without using tyre friction budget.

The implementation first computes tyre-limited deceleration, then adds

$$
a_{drag} = \frac{F_{drag}}{m}
$$

This means aero can hurt acceleration and top speed while helping braking zones.

## Braking realism gate
The default model should not need a hard-coded braking-g clip to look plausible.
If `solver.max_brake_decel_g` is present, it is an explicit experiment or safety override, not the normal realism mechanism.

The braking realism eval checks that the default run has no hard brake deceleration cap configured and that no brake deceleration cap events are active.
It also reports the static longitudinal tyre cap and an estimate of the older double-scaling behaviour where `base_mu` multiplied an already frictional tyre-data peak.

Code path

- [tools/evals/evaluate_braking_model.py](../../tools/evals/evaluate_braking_model.py)

## Diagnostics to inspect
Use these channels when braking behaviour looks suspicious.

- `backward_limiting_mode`
- `backward_brake_force_limit`
- `backward_brake_decel_limit_raw`
- `backward_brake_decel_limit`
- `backward_tyre_lateral_cap`
- `backward_combined_budget_scale`
- `backward_brake_decel_capped`
- `backward_brake_decel_cap_applied_events`
- `backward_front_normal_load_per_tyre`
- `backward_rear_normal_load_per_tyre`

Interpretation guide

- `brake_limited` means braking capability controlled the profile.
- `lateral_saturated` means lateral demand consumed almost all tyre budget.
- `corner_capped` means the local corner ceiling was lower than the braking propagation result.
- Non-zero `backward_brake_decel_cap_applied_events` means a hard braking clip affected the result. Treat as a diagnostic warning.

## Assumptions and limits
- Braking is quasi-static over each segment.
- Brake balance, ABS behaviour, tyre thermal state, and hydraulic dynamics are not modelled in detail.
- Drag is treated as an external deceleration term outside the tyre friction budget.
- The combined budget is a compact approximation, not a full transient combined-slip tyre model.

## Verification checks
Useful checks include

- [tools/evals/evaluate_braking_model.py](../../tools/evals/evaluate_braking_model.py)
- [tests/test_limiting_case_contracts.py](../../tests/test_limiting_case_contracts.py)
- [tests/test_falsification_and_scenario_contracts.py](../../tests/test_falsification_and_scenario_contracts.py)
- [src/ab_testing/run_ab_suite.py](../../src/ab_testing/run_ab_suite.py)

Milestone 5 includes synthetic straight-line accel and brake checks as part of the validation hierarchy.

## Next lesson
- [Vehicle Modelling Capstone](Vehicle-Modelling.md)

## Related lessons
- [Tyre Model Deep Dive](Tyre-Model-Deep-Dive.md)
- [Load Transfer and Normal Loads](Load-Transfer-and-Normal-Loads.md)
- [Vehicle Modelling Diagnostics and Trust Checks](Vehicle-Modelling-Diagnostics.md)
- [Numerical Robustness and Solver Failure Modes](Numerical-Robustness-and-Solver-Failure-Modes.md)
- [Lessons Index](README.md)
