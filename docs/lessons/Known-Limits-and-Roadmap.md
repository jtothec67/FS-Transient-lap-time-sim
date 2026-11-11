# Known Limits and Roadmap

## Purpose
This page lists what the simulator does not capture.
Each item is stated plainly with a brief note on the planned improvement.
The tone is honest, not defensive.
An attentive senior reviewer would correctly identify every item here.

## No lateral load transfer
Each axle's inner and outer tyres carry equal load in the current model.
There is no per-tyre lateral load distribution.

Why this matters. Tyre force capacity is a concave function of normal load.
Equal load split always overstates combined axle grip compared to the real case where the outer tyre is overloaded and the inner tyre is lightly loaded.
Cornering grip is therefore systematically overstated.

Roadmap. Add lateral load transfer using

$$
\Delta F_{z,lat} = \frac{m \cdot a_{lat} \cdot h}{t_{axle}}
$$

with a configurable roll stiffness distribution between front and rear axles.

## Longitudinal load transfer lags by one segment
The forward and backward passes compute load transfer using the kinematic acceleration estimate from the previous segment.
This is a one-step lag.
Load transfer at segment i uses the acceleration estimate from segment i-1.

Why this matters. Near rapid transitions like braking into a corner, the computed load state can be slightly mismatched.
For the majority of segments the lag is small.

Roadmap. Iterate to a fixed point at each segment until the load state and the acceleration estimate are mutually consistent.

## Corner equilibrium solver fixes Fx equal to zero
The apex speed solve sets longitudinal force to zero.
It does not account for the longitudinal force needed to overcome aerodynamic drag at the corner apex.

Why this matters. At 25 m/s with a drag area of approximately 0.64 m², aerodynamic drag is around 250 N.
That force is silently ignored in the corner speed solve.
Corner speeds are therefore slightly optimistic when drag is significant.

Roadmap. Include the drag-balance longitudinal force in the corner equilibrium residual.

## No tyre relaxation length
The tyre model is steady-state Pacejka.
There is no relaxation length dynamics.
Tyre force responds instantly to slip input changes.

Why this matters. Rapid slip transients in real tyres are filtered by the relaxation length.
The model cannot represent the transient force build-up during aggressive steering or throttle changes.

Roadmap. Add a first-order relaxation filter on slip inputs, parameterised by relaxation length in metres.

## No yaw inertia
The corner solver satisfies force and moment balance but does not include yaw inertia in the equilibrium.
The model assumes instantaneous yaw response.

## No gear shift time cost
The powertrain model always selects the best-case gear with zero shift time.
Real gear changes remove traction force for a short duration and add measurable lap time penalty on shifter cars.

## No engine braking
Engine braking is not modelled in the backward braking pass.
Available deceleration from engine drag is therefore understated on overrun.

## No rolling resistance
Rolling resistance is not included in the longitudinal force budget.
Net traction force is slightly overstated on low-speed and low-power segments.

## No driver model
Throttle is hardcoded to 1.0 in the forward acceleration pass.
There is no partial throttle, no corner exit ramp, and no driver style representation.

## Track elevation not propagated
The track loader computes elevation angle at each point from the x, y, z coordinates.
That channel is stored but is not used in the lap solver.

The lap integration contains no `g * sin(slope)` term in net longitudinal force.
Every segment is treated as flat.

On a real hilly track, climbing segments will produce optimistic speed predictions and descending segments will understate braking effort.
Lap time on a track with significant elevation change will be biased.

Roadmap. Add `F_{elevation} = m \cdot g \cdot \sin(\theta_{elevation})` to the longitudinal force budget in both forward and backward passes.

## TTC load sensitivity may extrapolate linearly above measured load range
The Pacejka-style interpolation uses the tabulated D values at each measured load level.
Above the highest measured load, the model extrapolates with whatever linear trend the interpolator produces.
This can inflate tyre force at very high normal loads.

A `peak_load_clamp` variant is available.
It gates tyre force at high loads using a configurable maximum growth ratio.
Use the clamped variant for operating points near or above the upper edge of the measured load range.

## `mu_scale` was previously applied at multiple sites
Historical versions of the model applied `base_mu` scaling at more than one location in the call chain.
This was consolidated. See code comments in `baseTyre.py` and `calcSpeedProfile.py` for details.
If you are working from an older branch, verify that friction scaling is not being double-applied.

## What this list is not
This list does not claim the simulator is unreliable for its intended use.
For parameter sensitivity studies, setup direction comparisons, and A/B ranking of configurations on a flat track, the model is well-validated and fast.
These are the known boundaries, stated so reviewers and users can apply the right level of caution.

## Related lessons
- [Simulator Summary and Core Solver](simulator-summary.md)
- [Tyre Model Deep Dive](Tyre-Model-Deep-Dive.md)
- [Vehicle Modelling Diagnostics and Trust Checks](Vehicle-Modelling-Diagnostics.md)
- [Lessons Index](README.md)
