# Numerical Robustness and Solver Failure Modes

## Read this after
Read [Simulator Summary and Core Solver](simulator-summary.md) first.

## Goal
Explain how the solver decides whether a corner solution is valid, what fallback means, and which gates prevent numerical behaviour from becoming hidden performance.

## One minute mental model
The corner solver is allowed to fail.
What matters is that failure is visible, bounded, and physically conservative.

A successful point solves equilibrium.
A fallback point uses a constrained speed estimate and records that the normal solve did not succeed.

## Corner solve structure
The corner solve has two nested pieces.

1. An outer bisection searches for the highest feasible speed.
2. An inner root solve searches for steering angle and sideslip angle at that speed.

Code path

- [src/simulator/util/vehicleDynamics.py](../../src/simulator/util/vehicleDynamics.py) `find_vehicle_state_at_point`
- [src/simulator/util/calcSpeedProfile.py](../../src/simulator/util/calcSpeedProfile.py) `optimise_speed_at_points`

## Equilibrium residuals
At a candidate speed, the solver checks lateral force balance:

$$
m v^2 \kappa = F_{y,f} + F_{y,r}
$$

It also checks yaw moment balance about the centre of gravity:

$$
a F_{y,f} = b F_{y,r}
$$

The root solver success flag alone is not enough.
The code also checks absolute and relative residuals.
The inner root solve is explicitly solving for steering angle $\delta$ and vehicle sideslip $\beta$ so that lateral force balance and yaw moment balance are both satisfied.

Diagnostics include

- `corner_solver_lat_residual_abs`
- `corner_solver_yaw_residual_abs`
- `corner_solver_lat_residual_rel`
- `corner_solver_yaw_residual_rel`

## Retry tiers
The speed profile code tries a small set of solve tiers:

- `base`
- `warm_start`
- `conservative_bound`

Warm start uses a nearby previous solution as the initial guess.
The conservative tier lowers the bound to make the solve easier.
These tiers are for numerical robustness, not for granting extra performance.

Diagnostics include

- `corner_retry_count`
- `corner_solve_method`
- `corner_tier_failure_reasons`

## Fallback behaviour
If all solve tiers fail, the point uses a fallback speed.
That fallback is bounded by three ideas:

- a tyre-friction speed estimate from `base_mu`,
- physical cap speed from rollover and tyre lateral limits,
- continuity cap from the previous point speed.

The important point is that the fallback speed itself is bounded.
It is not allowed to become an unconstrained performance estimate.

Code path

- [src/simulator/util/calcSpeedProfile.py](../../src/simulator/util/calcSpeedProfile.py) `_compute_constrained_fallback_speed`

The fallback point is marked in diagnostics:

- `corner_solver_success = False`
- `corner_fallback_used = True`
- `corner_fallback_speed`
- `corner_failure_reason`

## Why fallback can be risky
Fallback is useful because a few numerical misses should not destroy a full lap run.
It is risky because a too-generous fallback could accidentally increase performance.

The controls against that risk are:

- physical caps,
- continuity caps,
- explicit fallback flags,
- fallback-rate gates,
- solver-success-rate gates,
- solver success gates from residual checks,
- g-channel spike checks.

Milestone 4 exists to make sure numerical robustness does not leak physics.

## Diagnostics to inspect
Start with

- `corner_solver_success`
- `corner_fallback_used`
- `corner_retry_count`
- `corner_failure_reason`
- `corner_physical_cap_speed`
- `corner_solver_lat_residual_rel`
- `corner_solver_yaw_residual_rel`

Then check whether the final lap has strange g spikes in [Vehicle Modelling Diagnostics and Trust Checks](Vehicle-Modelling-Diagnostics.md).

## Assumptions and limits
- The corner solve is a steady-state bicycle-style equilibrium.
- The fallback is a bounded approximation, not a solved vehicle state.
- Residual thresholds are engineering gates, not proof of full physical truth.
- A low fallback count is acceptable only when the rest of the diagnostics remain credible.

## Verification checks
Useful commands:

```bash
uv run python -m unittest tests.test_solver_contracts tests.test_limiting_case_contracts -v
uv run python src/ab_testing/run_ab_suite.py --tracks FSUK,SkidpadF26,StraightLineTrack --variants baseline --output-dir ab_test_outputs/m4_hard_gate --fallback-threshold 0.15 --stale-threshold 0.05 --max-out-of-domain-count 130000 --enforce-milestone4-gates
```

## Next lesson
- [Vehicle Modelling Diagnostics and Trust Checks](Vehicle-Modelling-Diagnostics.md)

## Related lessons
- [Vehicle Modelling Capstone](Vehicle-Modelling.md)
- [Simulator Summary and Core Solver](simulator-summary.md)
- [Braking Dynamics and Deceleration Budget](Braking-Dynamics-and-Deceleration-Budget.md)
- [Validation and Falsification Workflow](Validation-and-Falsification-Workflow.md)
- [Lessons Index](README.md)
