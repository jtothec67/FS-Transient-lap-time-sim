# Simulator Basics

## Read this after
Start here if you are new to the simulator.

## Audience
This note is for new readers who want a clear first mental model of the simulator.

## Goal
Explain what this simulator is trying to do.
Explain what quasi static and steady state mean in this project.
Explain how tyre, powertrain, aero, and constraints are combined into one lap result.

## What is a simulator trying to do
At a high level, this simulator predicts lap behaviour from a set of assumptions and parameters.
It is a decision support model, not a replacement for real testing.

The model takes

- vehicle parameters
- track geometry
- tyre and powertrain maps

It returns

- speed profile around the lap
- lap time estimate
- diagnostic channels that explain what limited speed at each segment

## What quasi static means here
Quasi static means we model each local point as if it is close to equilibrium.
We do not integrate full fast transient dynamics at each subsystem state.

In this project that means

- no full suspension transient state history in the core solver
- no full tyre thermal transient state history in the core solver
- loads and forces are solved with compact algebraic relations at each step

Why this choice was made

- it is fast enough for sweeps and A B comparisons
- it is stable enough for parameter sensitivity work
- it is simple enough to debug and trust channel by channel

## What steady state means here
Steady state means force and moment balances are solved for a point as if the state is not rapidly changing during that solve.

In corner analysis that means

- lateral force balance is satisfied
- yaw moment balance is satisfied
- tyre forces are evaluated at the current local load and slip assumptions

Steady state is used inside local solves.
Quasi static describes the broader modelling strategy across the lap.

Think of a flipbook of the lap.
Quasi static is the choice to analyse one frame at a time with compact physics.
Steady state is what each frame is trying to satisfy before moving to the next frame.

## How we combine subsystems into one simulator
This is the runtime chain at a basic level.

1. Load vehicle parameters from [parameters.json](../../parameters.json) and model config from [config.json](../../config.json).
2. Build tyre model from [src/vehicle/Tyres/baseTyre.py](../../src/vehicle/Tyres/baseTyre.py).
3. Build powertrain model from [src/vehicle/Powertrain/basePowertrain.py](../../src/vehicle/Powertrain/basePowertrain.py).
4. Build vehicle object in [src/vehicle/vehicle.py](../../src/vehicle/vehicle.py).
5. Solve corner-limited speed with the corner equilibrium path in [src/simulator/util/vehicleDynamics.py](../../src/simulator/util/vehicleDynamics.py).
6. Run forward pass for acceleration with powertrain force, tyre limits, and drag in [src/simulator/util/calcSpeedProfile.py](../../src/simulator/util/calcSpeedProfile.py).
7. Run backward pass for braking limits in [src/simulator/util/calcSpeedProfile.py](../../src/simulator/util/calcSpeedProfile.py).
8. Combine constraints into final speed profile and lap time output in [src/simulator/simulator.py](../../src/simulator/simulator.py).

## A compact force picture
At each segment, one useful way to think is

- powertrain requests longitudinal force
- tyre envelope caps what is physically available
- lateral demand consumes part of grip budget
- drag and other resistances reduce net acceleration

A compact longitudinal step is

$$
F_{x,net} = \min\!\left(F_{x,power},\ F_{x,tyre\_cap} \cdot \sqrt{1 - \left(\frac{F_{y,demand}}{F_{y,cap}}\right)^2}\right) - F_{drag}
$$

The friction-ellipse term inside the min reduces available longitudinal force when lateral demand is present.
When the car is on a straight with no lateral demand, the term equals 1 and the equation reduces to the simpler tyre-cap limit.

The tyre model supplies the contact patch force limits.
The powertrain model supplies torque and wheel force request.
The geometry and aero model supply loads and demands.

## Tradeoffs when using this simulator
Benefits

- fast iteration for design and sensitivity studies
- transparent equations with traceable code paths
- practical for setup direction and parameter ranking

Tradeoffs

- not a full transient multi body simulation
- limited direct modelling of tyre thermal and pressure evolution
- limited direct modelling of suspension transient behaviour
- results depend on map quality and parameter realism

How to use results well

- use trends and deltas as the primary signal
- validate key findings with higher fidelity tools or test data
- treat out of domain diagnostics as a stop sign

## Suggested reading order
1. [Tyre Model Intro](Tyre-Model.md)
2. [Powertrain Model and Wheel Force Flow](Powertrain-Model.md)
3. [Aerodynamics Model Intro](Aero-Model.md)
4. [Vehicle Modelling Capstone](Vehicle-Modelling.md)
5. [Simulator Summary and Core Solver](simulator-summary.md)
6. [Vehicle Modelling Diagnostics and Trust Checks](Vehicle-Modelling-Diagnostics.md)
7. [Track Geometry and Sampling for Vehicle Dynamics](Track-Geometry-and-Sampling.md)

Optional side path after Tyre Model Intro

- [Tyre Model Deep Dive](Tyre-Model-Deep-Dive.md)

## Next lesson
- [Tyre Model Intro](Tyre-Model.md)

## Related lessons
- [Lessons Index](README.md)
- [Parameter Enforcement Audit Roadmap](../PARAMETER_ENFORCEMENT_AUDIT_ROADMAP.md)
- [Major Change Log](../MAJOR_CHANGE_LOG.md)
