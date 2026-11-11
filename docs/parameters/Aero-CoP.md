# Aero CoP (Aerodynamic Centre of Pressure)

Purpose: explain what the `aero_cp` parameter means, how it maps to real physics, and how it is enforced in the simulator.

## 1) What This Parameter Represents

`aero_cp` is the longitudinal position of aerodynamic center of pressure (CoP), measured from the front axle.

- Units: m
- Physical range: `[0, wheelbase]`
- Mapping:
  - `0` means aero load acts at the front axle.
  - `wheelbase` means aero load acts at the rear axle.

In the simulator, this is loaded as `aero_centre_of_pressure`.

## 2) First-Principles Physics

At speed, total aerodynamic downforce is computed as:

$$
F_{aero} = \tfrac{1}{2}\rho C_L A v^2
$$

where:
- $\rho$ is air density,
- $C_L$ is downforce coefficient,
- $A$ is frontal area,
- $v$ is vehicle speed.

CoP determines where this total vertical load is applied along the wheelbase. Using static moment equilibrium:

$$
F_{rear,aero} = F_{aero}\frac{x_{cp}}{L}, \qquad
F_{front,aero} = F_{aero}\left(1-\frac{x_{cp}}{L}\right)
$$

where:
- $x_{cp}$ is CoP distance from front axle,
- $L$ is wheelbase.

Key invariant:

$$
F_{front,aero} + F_{rear,aero} = F_{aero}
$$

So CoP redistributes aero load front/rear without changing total aero load.

## 3) Why It Matters Laterally (Even in a Single-Track Model)

Yes, it affects lateral behavior.

Even without a full two-track bicycle model, front/rear normal loads influence front/rear tyre force capacity and yaw balance. In this solver, changing CoP changes axle normal loads, which changes feasible corner equilibrium (steer angle, sideslip, and speed).

What it affects now:
- Front vs rear grip balance through normal-load redistribution.
- Yaw/lateral equilibrium through axle-specific tyre forces.

What it does not capture (current model limitation):
- Left-right inner/outer wheel load split.
- Per-wheel nonlinear saturation differences on each axle.
- Detailed roll-couple distribution and camber-jacking effects.

## 4) How It Is Implemented in the Simulator

1. Total aero downforce is computed from speed.
2. CoP-based split computes front/rear aero axle loads.
3. Those are combined with gravity split and longitudinal transfer.
4. Axle-specific per-tyre normal loads are passed into corner equilibrium solver.

Implementation references:
- Downforce calculation: `src/vehicle/vehicle.py` (`compute_downforce`)
- CoP split helper: `src/simulator/util/calcSpeedProfile.py` (`_split_aero_load_by_cp`)
- Longitudinal normal-load state: `src/simulator/util/calcSpeedProfile.py` (`_compute_normal_loads_for_longitudinal`)
- Corner equilibrium with axle-specific loads: `src/simulator/util/vehicleDynamics.py` (`find_vehicle_state_at_point`)

## 5) Validation Evidence Added

Contracts implemented:
- `test_aero_cp_shifts_front_rear_load_distribution`
- Total normal-load invariance check at fixed speed/mass.

File:
- `tests/test_parameter_enforcement_contracts.py`

Observed behavior in focused probe:
- CoP change produced non-zero lap-time delta on FSUK, confirming runtime sensitivity.

## 6) Engineering Interpretation and Tuning Guidance

Directionally:
- More front-biased CoP increases front axle aero load.
- More rear-biased CoP increases rear axle aero load.

Practical meaning:
- CoP is a balance parameter, not a total-grip parameter.
- Use it to tune front/rear aero balance while keeping total downforce model unchanged.

Guardrails:
- Keep CoP within `[0, wheelbase]` for physical realism.
- Interpret lap-time deltas together with handling balance metrics, not in isolation.

## 7) Current Scope and Future Work

Current scope:
- Quasi-static axle-level effect is enforced and tested.

Potential future upgrades:
- Two-track (left-right) load transfer integration with aero distribution.
- Coupled aero-map behavior (speed, ride height, pitch sensitivity).
- Additional contracts linking CoP movement to understeer/oversteer indicators.

---

## Template For Future Parameter Docs

Use this structure for each parameter page:
1. What it represents (definition, units, valid range)
2. First-principles equation(s)
3. Why it matters physically
4. How it is implemented in sim (functions/files)
5. Validation evidence (tests, probes, gate signals)
6. Tuning guidance and caveats
7. Scope limits and future work
