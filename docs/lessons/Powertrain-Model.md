# Powertrain Model and Wheel Force Flow

## Read this after
Read [Tyre Model Intro](Tyre-Model.md) first.

## Audience
This note is for developers who need to understand how the simulator turns RPM and gearing into longitudinal force.

## Goal
Explain the first-principles powertrain chain used in this repository, how wheel radius enters the equations, and how powertrain force is combined with tyre limits in lap simulation.

## Starting Point
The production path uses

- lookup-table power data for the power unit
- drivetrain ratios and efficiency from vehicle parameters
- wheel-radius conversion from torque to force

Current default configuration uses Honda CBR600RR power data in [config.json](../../config.json).

## First Principles View
At the wheel hub, power and torque are related by

$$
P = T \omega
$$

At the contact patch, longitudinal force from wheel torque is

$$
F_{x,traction} = \frac{T_{wheel}}{r_w}
$$

So a larger wheel radius reduces traction force for the same wheel torque.

## Runtime Model in This Repository

### 1) Power curve lookup
Powertrain data is loaded by [src/vehicle/Powertrain/basePowertrain.py](../../src/vehicle/Powertrain/basePowertrain.py).

- If available, it uses `Continuous Power [kW]`
- Otherwise it falls back to `Peak Power [kW]`

Default data file

- [datasets/vehicle/PU_data/Honda_CBR_600RR_RPM_vs_Peak_Power.csv](../../datasets/vehicle/PU_data/Honda_CBR_600RR_RPM_vs_Peak_Power.csv)

The default dataset name includes "Peak Power".
The current `config.json` points to this Peak Power dataset, so the active operating curve IS peak power.
The continuous power fallback path is not in use with the shipped configuration.
Lap time results reflect peak-output operation throughout, not a derated continuous limit.

### 2) Torque from power
The model computes torque from lookup power as

$$
T_{engine}(rpm) = \frac{P(rpm) \cdot 1000 \cdot 60}{2\pi \cdot rpm}
$$

This is implemented in `LookupTablePowertrainModel.get_torque`.

### 3) Speed to engine RPM
Vehicle speed is mapped to engine RPM in [src/vehicle/vehicle.py](../../src/vehicle/vehicle.py)

$$
rpm = \frac{v \cdot 60 \cdot (g_i \cdot g_f)}{2\pi r_w}
$$

Where

- $g_i$ is selected gear ratio
- $g_f$ is final drive ratio
- $r_w$ is wheel radius

### 4) Wheel torque through drivetrain
Wheel torque is

$$
T_{wheel} = T_{engine} \cdot g_i \cdot g_f \cdot \eta_{tr}
$$

Where $\eta_{tr}$ is transmission efficiency.

### 5) Traction force at contact patch
Powertrain-limited traction force is

$$
F_{x,power} = \frac{T_{wheel}}{r_w}
$$

## Where wheel_radius matters
`wheel_radius` is active in two places.

1. RPM mapping
A larger radius reduces RPM at a fixed vehicle speed.

2. Torque-to-force conversion
A larger radius reduces contact-patch force for the same wheel torque.

This is why `wheel_radius` has direct monotonic contracts in [tests/test_parameter_enforcement_contracts.py](../../tests/test_parameter_enforcement_contracts.py).

## Gear Selection Logic
At each speed step, the solver tries all configured gear ratios and selects the one with maximum net longitudinal force.

Entry point

- `Vehicle.select_optimal_gear` in [src/vehicle/vehicle.py](../../src/vehicle/vehicle.py)

## Coupling with Tyre Model and base_mu
The forward pass in [src/simulator/util/calcSpeedProfile.py](../../src/simulator/util/calcSpeedProfile.py) uses

1. Powertrain-limited force from wheel torque and wheel radius
2. Tyre-limited longitudinal cap from tyre model
3. Combined-slip budget reduction under lateral demand
4. Aerodynamic drag subtraction

Implemented net step

$$
F_{x,net} = \min\!\left(F_{x,power},\ F_{x,tyre\_cap} \cdot \sqrt{1 - \left(\frac{F_{y,demand}}{F_{y,cap}}\right)^2}\right) - F_{drag}
$$

The friction-ellipse term reduces available longitudinal force when lateral demand is present.
The full formula is computed in `_longitudinal_budget_scale_from_lateral_demand` inside
[src/simulator/util/calcSpeedProfile.py](../../src/simulator/util/calcSpeedProfile.py).

`base_mu` primarily acts on tyre force capability, not on engine torque generation.
So `base_mu` belongs in tyre explanation, while `wheel_radius` belongs in powertrain explanation.
Both must be cross-linked because acceleration depends on both.

## Validation and Contracts
Relevant direct checks

- [tests/test_parameter_enforcement_contracts.py](../../tests/test_parameter_enforcement_contracts.py)

Covered monotonic relationships include

- higher `transmission_efficiency` gives higher wheel torque
- higher `final_drive_ratio` gives higher wheel torque
- larger `wheel_radius` gives lower traction force
- higher `gear_ratio` gives higher wheel torque at fixed RPM

## Known Limits
Current powertrain model is compact and quasi-static.
It does not currently model

- clutch dynamics and shift transients
- traction control actuation
- engine inertia and transient torque dynamics
- thermal derating and fuel constraints
- gear shift time cost. the solver always picks the best-case gear with zero shift delay
- throttle is hardcoded to 1.0 throughout the forward pass, there is no partial-throttle model
- engine braking is not modelled in the backward braking pass

This tradeoff keeps runtime fast and stable for sweep-heavy lap studies.

## Next lesson
- [Aerodynamics Model Intro](Aero-Model.md)

## Related Lessons
- [Simulator Basics](Simulator-Basics.md)
- [Tyre Model Intro](Tyre-Model.md)
- [Aerodynamics Model Intro](Aero-Model.md)
- [Vehicle Modelling Capstone](Vehicle-Modelling.md)
- [Simulator Summary and Core Solver](simulator-summary.md)
- [Vehicle Modelling Diagnostics and Trust Checks](Vehicle-Modelling-Diagnostics.md)
- [Track Geometry and Sampling for Vehicle Dynamics](Track-Geometry-and-Sampling.md)
- [Lessons Index](README.md)
