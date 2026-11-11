# Milestone 1: Equations and Units Audit

Purpose: establish a single source of truth for governing equations, units, and sign conventions used by the current quasi-static solver path.

Status: in progress

## 1) Sign Conventions

- Curvature `K` [1/m]: sign indicates turn direction; magnitudes are used in cap logic where direction is irrelevant.
- Lateral tyre forces `Fy_f`, `Fy_r` [N]: positive values follow current tyre model sign convention.
- Steering angle `delta` [rad internal, deg at API boundaries].
- Sideslip angle `beta` [rad internal, deg at API boundaries].

## 2) Governing Equations

### Corner equilibrium solver

Implemented in `find_vehicle_state_at_point`.

- Lateral force balance:

$$
m v^2 K = F_{y,f} + F_{y,r}
$$

- Yaw moment balance about CoG:

$$
a F_{y,f} = b F_{y,r}
$$

- Slip-angle relations (small-angle bicycle form):

$$
\alpha_f = \delta - \beta - aK
$$

$$
\alpha_r = -\beta + bK
$$

### Rollover speed bound

Used as a hard upper bound in corner solving and speed-cap composition.

$$
v_{roll} = \sqrt{\frac{t}{2h} g R}, \quad R = \frac{1}{|K|}
$$

### Forward-pass speed propagation

$$
v_{i,pred}^2 = v_{i-1}^2 + 2 a_{x,i} \Delta s
$$

with

$$
a_{x,i} = \frac{F_{x,i}}{m}, \quad F_{x,i} = F_{traction,i} - F_{drag,i}
$$

### Backward-pass braking propagation

$$
v_{i,brake}^2 = v_{i+1}^2 + 2 a_{brake,i} \Delta s
$$

with friction-budgeted braking and drag contribution.

## 3) Units Audit Table

- `m` mass: kg
- `v` speed: m/s
- `K` curvature: 1/m
- `R` radius: m
- `F` forces: N
- `M` moments: N m
- `a` accelerations: m/s^2
- `delta`, `beta`, `alpha`: rad internal, deg at tyre API boundary
- `t`, `h`, `a`, `b`, `L`, `ds`: m

Audit rule: each additive equation must sum same dimensions on both sides.

## 4) Current Limiting-Case Contracts

The following contracts are now covered by dedicated tests:

- Near-zero curvature returns straight-cap speed and zero steer/sideslip.
- Sign-convention symmetry for mirrored turns:
	- `+K` and `-K` produce matching corner speed caps.
	- steering and sideslip angles are equal-magnitude with opposite sign.
- Core equation dimensions are asserted explicitly:
	- lateral balance `m v^2 K` vs tyre force sum
	- yaw balance `a Fy` vs `b Fy`
	- rollover-cap inner term vs speed-squared units
	- kinematic propagation term consistency `v^2` and `a ds`
- Longitudinal combined-slip budget scale remains bounded in [0, 1] with expected endpoints.
- Zero powertrain torque does not create forward acceleration on a straight segment.
- Zero-speed backward propagation remains stationary.
- Corner-equilibrium residual telemetry exists and is finite for solved points:
	- `corner_solver_lat_residual_abs`
	- `corner_solver_yaw_residual_abs`
	- `corner_solver_lat_residual_rel`
	- `corner_solver_yaw_residual_rel`

## 5) Open Follow-Ups

- Add residual trend thresholds (p90/max guardrails) into CI-style gates once baseline distributions are fixed.

## 6) Lint-Style Constant Scan

To enforce the Milestone 1 "no undocumented constants" rule on core solver files, run:

```bash
uv run python tools/analysis/m1_magic_constant_scan.py --strict
```

This scan is AST-based and currently targets:
- `src/simulator/util/vehicleDynamics.py`
- `src/simulator/util/calcSpeedProfile.py`