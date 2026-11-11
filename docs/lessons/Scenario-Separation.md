# Scenario Separation

## Read this after
Read [Calibration and Sensitivity Workflow](Calibration-and-Sensitivity-Workflow.md) first.

## Goal
Explain the difference between base vehicle parameters and scenario effects, and show how the simulator keeps those effects separate.

## One minute mental model
The base vehicle is the car.
The scenario is the world the car is running in.

Changing the weather or track condition should not rewrite the car's calibrated tyre or aero parameters.
Instead, scenario multipliers sit on top of the base vehicle model.

## Base vehicle parameters
Base vehicle parameters describe the car itself.

Examples

- mass
- wheelbase
- centre of gravity height
- wheel radius
- base tyre grip parameter
- aero coefficients
- aero centre of pressure

These should remain stable when comparing scenarios.

## Scenario parameters
Scenario parameters describe operating conditions.

Current scenario context includes

- `scenario.name`
- `scenario.grip_scale`
- `scenario.air_density_scale`

Code path

- [src/simulator/util/calcSpeedProfile.py](../../src/simulator/util/calcSpeedProfile.py) `_get_scenario_context`
- [src/vehicle/vehicle.py](../../src/vehicle/vehicle.py)
- [src/ab_testing/run_ab_suite.py](../../src/ab_testing/run_ab_suite.py)

## Good scenario implementation
A good wet-track scenario might set

```json
{
  "scenario": {
    "name": "wet_track",
    "grip_scale": 0.9,
    "air_density_scale": 0.97
  }
}
```

The base `base_mu` remains the same.
The scenario grip multiplier changes the operating condition.

Note on air density direction. Wet air is less dense than dry air at the same temperature.
Water vapour displaces heavier nitrogen and oxygen molecules, so humid or wet conditions reduce air density slightly.
A value below 1.0 is physically correct for a wet-weather scenario.
A value above 1.0 represents a cold dry morning or a higher-altitude air density increase.

## Bad scenario implementation
A bad implementation would silently lower `base_mu` and then call that the wet setup.

That is a problem for these reasons

- the vehicle calibration has been changed
- dry and wet comparisons no longer share the same base truth
- future calibration work cannot tell whether a change came from the car or the scenario
- A/B reports lose context

## Runtime reporting
A/B outputs include explicit scenario context

- `scenario_name`
- `scenario_grip_scale`
- `scenario_air_density_scale`

Milestone 6 gates check that scenario context is present and multipliers are positive.

## Relationship to validation
Scenario separation depends on the earlier validation gates.
The baseline vehicle should pass physics and realism gates before scenario effects are layered on top.

Then scenario-only changes should produce expected directions without violating realism gates.

Examples

- lower grip scale should usually reduce grip-limited performance
- higher air density can increase drag and downforce together
- scenario changes should not create non-physical normal-load events

## Assumptions and limits
- Current scenario support is intentionally compact.
- Grip scaling is a simplified representation of track condition.
- Air-density scaling is a simplified representation of weather or altitude.
- Detailed tyre temperature, water film, wind direction, and transient weather effects are outside the current core model.

## Verification checks
Useful commands

```bash
uv run python -m unittest tests.test_falsification_and_scenario_contracts -v
uv run python src/ab_testing/run_ab_suite.py --tracks FSUK,SkidpadF26,StraightLineTrack --variants baseline --output-dir ab_test_outputs/m6_hard_gate --fallback-threshold 0.15 --stale-threshold 0.05 --max-out-of-domain-count 130000 --enforce-milestone3-gates --enforce-milestone4-gates --enforce-milestone5-gates --enforce-milestone6-gates --scenario-name baseline --scenario-grip-scale 1.0 --scenario-air-density-scale 1.0 --m5-max-abs-glat-g 2.0 --m5-max-gtotal-g 4.45
```

## Next lesson
- [Lessons Index](README.md)

## Related lessons
- [Calibration and Sensitivity Workflow](Calibration-and-Sensitivity-Workflow.md)
- [Validation and Falsification Workflow](Validation-and-Falsification-Workflow.md)
- [Vehicle Modelling Diagnostics and Trust Checks](Vehicle-Modelling-Diagnostics.md)
- [Vehicle Analysis IRL vs Simulator and GG Envelope](Vehicle-Analysis-IRL-vs-Simulator.md)
- [Lessons Index](README.md)
