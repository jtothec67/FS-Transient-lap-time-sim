# Tyre Model Deep Dive

## Read this after
Read [Simulator Basics](Simulator-Basics.md) and [Tyre Model Intro](Tyre-Model.md) first.

## Audience
This note is for readers who already finished [Simulator Basics](Simulator-Basics.md) and [Tyre Model Intro](Tyre-Model.md).

## Goal
Give a deeper technical view of how tyre force is represented in this repository.
Show the main equations, the runtime path, and the current modelling limits.

## First principles reminder
At the contact patch, traction is distributed over area.
The net force and moment come from area integrals.

$$
\mathbf{F} = \int_A \mathbf{t}(x,y)\,dA
$$

$$
\mathbf{M}_O = \int_A \mathbf{r}(x,y) \times \mathbf{t}(x,y)\,dA
$$

For the current lap solver we mostly use in plane force channels and their resultant

$$
F_{xy} = \sqrt{F_x^2 + F_y^2}
$$

## Magic Formula context
The tyre force curves use a Pacejka style form fit to measured data.
A common pure slip shape is

$$
F(x) = D \sin\left(C \arctan\left(Bx - E\left(Bx - \arctan(Bx)\right)\right)\right)
$$

Where

- $x$ is slip input
- $D$ is force scale at current load
- $B$ controls initial slope region
- $C$ controls curve shape
- $E$ controls shoulder and peak region

This is an empirical model family.
It is fit to data and not derived from full contact patch material mechanics.

## Runtime path in this repository
Primary implementation path

- [src/vehicle/Tyres/baseTyre.py](../../src/vehicle/Tyres/baseTyre.py)

Runtime call chain

1. Parameters are loaded in [src/vehicle/vehicle.py](../../src/vehicle/vehicle.py).
2. Tyre model object is created through `create_tyre_model`.
3. Corner and speed profile routines call pure and combined tyre force methods.
4. Limits are consumed by corner equilibrium and longitudinal passes.

Related solver paths

- [src/simulator/util/vehicleDynamics.py](../../src/simulator/util/vehicleDynamics.py)
- [src/simulator/util/calcSpeedProfile.py](../../src/simulator/util/calcSpeedProfile.py)

## Load sensitivity and base_mu
The model uses load dependent peak interpolation from TTC style datasets.
A global scale `base_mu` is applied against a dataset reference friction level.

Conceptually

$$
\mu_{lat,ref} = median\left(\frac{D_{lat,table}(F_z)}{F_z}\right)
$$

$$
\mu_{long,ref} = median\left(\frac{D_{long,table}(F_z)}{F_z}\right)
$$

$$
D_{lat,used}(F_z) = D_{lat,table}(F_z) \cdot \frac{base\_mu}{\mu_{lat,ref}}
$$

$$
D_{long,used}(F_z) = D_{long,table}(F_z) \cdot \frac{base\_mu}{\mu_{long,ref}}
$$

This gives a controlled way to shift force capacity while preserving curve families.

## Combined slip treatment
The current combined slip path uses a capped resultant approach.

Pure channel forces are computed first.
Then total demand is checked

$$
F_{total} = \sqrt{F_x^2 + F_y^2}
$$

Cap is built from load dependent channel peaks

$$
F_{cap} = 0.9 \cdot \sqrt{D_{lat}^2 + D_{long}^2}
$$

If demand exceeds cap, both channels are scaled by

$$
scale = \frac{F_{cap}}{F_{total}}
$$

$$
F_x' = scale\,F_x, \qquad F_y' = scale\,F_y
$$

This preserves vector direction and enforces a consistent budget.
It is a practical approximation and not a full MF combined slip weighting model.

**Note on combined slip and the lap solver**

The tyre model class (`baseTyre.py`) exposes a `get_combined_forces` method that uses the elliptical-cap approach described above.
That method is available for general use but is NOT called by the lap solver.

The lap solver uses a separate friction-ellipse budget at the solver level.
The function is `_longitudinal_budget_scale_from_lateral_demand` in `calcSpeedProfile.py` (lines 268-274).
It computes

$$
\text{scale} = \sqrt{1 - \left(\frac{F_{y,demand}}{F_{y,cap}}\right)^2}
$$

and then multiplies the available longitudinal force cap by that scale.
This is the production path for both the forward acceleration pass and the backward braking pass.

Relevant files

- [src/vehicle/Tyres/baseTyre.py](../../src/vehicle/Tyres/baseTyre.py) defines `get_combined_forces` (not called by lap solver)
- [src/simulator/util/calcSpeedProfile.py](../../src/simulator/util/calcSpeedProfile.py) defines `_longitudinal_budget_scale_from_lateral_demand` (active lap solver path)

## Worked numeric example
Assume

- pure $F_y = 3800$ N
- pure $F_x = 3200$ N
- $D_{lat} = 4000$ N
- $D_{long} = 3200$ N

Cap

$$
F_{cap} = 0.9 \cdot \sqrt{4000^2 + 3200^2} \approx 4610\,N
$$

Demand

$$
F_{total} = \sqrt{3800^2 + 3200^2} \approx 4964\,N
$$

Scale

$$
scale = \frac{4610}{4964} \approx 0.929
$$

Returned

- $F_x' \approx 2973$ N
- $F_y' \approx 3530$ N

## Effective loaded radius note
Slip and kinematic relations in literature use effective rolling radius.
For free rolling relation

$$
V_x \approx r_e\Omega
$$

In Pacejka conventions, a common approximation for effective rolling radius is

$$
r_e \approx r_s - \frac{r_l - r_s}{3}
$$

where $r_s$ is the free static (unloaded) radius and $r_l$ is the loaded radius.
This places the effective rolling radius closer to the loaded radius than the free static radius.

So if `wheel_radius` does not represent a loaded effective value, speed to RPM and slip related computations can drift.
For this project, treating wheel radius as loaded effective radius is the healthier assumption.

## Validation and guardrails
Relevant tests and reports

- [tests/test_tyre_force_contracts.py](../../tests/test_tyre_force_contracts.py)
- [tests/test_tyre_validity_domain_contracts.py](../../tests/test_tyre_validity_domain_contracts.py)
- [tests/test_limiting_case_contracts.py](../../tests/test_limiting_case_contracts.py)
- [tools/analysis/compare_tyre_model.py](../../tools/analysis/compare_tyre_model.py)

Typical checks include

- zero and limiting behaviour
- out of domain counters
- clamping or flagging when slip or load leaves the declared validity domain
- RMSE validation against tyre data
- high load growth behaviour
- sensitivity gates on representative tracks

For the peak-load-clamped variant, high-load growth is gated so extrapolated tyre force cannot inflate unrealistically beyond the measured load range.
The validation command uses `--max-high-load-growth-ratio` to make that high-load growth gate explicit.

## Known limits
Current model does not include full transient tyre state evolution.
Examples

- relaxation length dynamics
- full temperature and pressure state evolution
- full aligning moment path in this compact workflow
- full carcass dynamics

These are deliberate tradeoffs for speed and robustness in lap sweeps.

## Next lesson
- [Powertrain Model and Wheel Force Flow](Powertrain-Model.md)

## Related lessons
- [Tyre Model Intro](Tyre-Model.md)
- [Powertrain Model and Wheel Force Flow](Powertrain-Model.md)
- [Load Transfer and Normal Loads](Load-Transfer-and-Normal-Loads.md)
- [Braking Dynamics and Deceleration Budget](Braking-Dynamics-and-Deceleration-Budget.md)
- [Validation and Falsification Workflow](Validation-and-Falsification-Workflow.md)
- [Known Limits and Roadmap](Known-Limits-and-Roadmap.md)
- [Lessons Index](README.md)

## References
- Pacejka, H. B. Tire and Vehicle Dynamics
- Bakker, Nyborg, Pacejka 1987 SAE tyre modelling paper https://www.theoryinpracticeengineering.com/resources/tires/pacejka87.pdf
- MathWorks Tire Road Interaction Magic Formula https://www.mathworks.com/help/sdl/ref/tireroadinteractionmagicformula.html
- x-engineer longitudinal Magic Formula summary https://x-engineer.org/automotive-engineering/chassis/vehicle-dynamics/tire-model-for-longitudinal-forces/
