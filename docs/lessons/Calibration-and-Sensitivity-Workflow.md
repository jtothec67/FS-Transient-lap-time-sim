# Calibration and Sensitivity Workflow

## Read this after
Read [Validation and Falsification Workflow](Validation-and-Falsification-Workflow.md) first.

## Goal
Explain how to change vehicle dynamics parameters responsibly, interpret sensitivity, and avoid hiding model errors through retuning.

## One minute mental model
Calibration is not "change values until lap time looks right."
It is a controlled process:

1. freeze a baseline,
2. change one thing,
3. compare outputs and diagnostics,
4. check whether the direction makes physical sense,
5. only then decide whether the parameter update is credible.

## Freeze the baseline
Before a parameter change, keep a known baseline config and representative outputs.

Record:

- lap time,
- peak lateral g,
- peak total g,
- fallback rate,
- solver success rate,
- normal-load events,
- tyre out-of-domain count,
- limiter mode mix.

This makes changes auditable.

## Change one parameter at a time
For first-pass sensitivity work, isolate the variable.

Examples:

- `base_mu` should affect tyre force capacity.
- `cog_z` should affect load transfer and rollover-related limits.
- `wheel_radius` should affect speed-to-RPM and wheel-force conversion.
- aero coefficients should affect drag, downforce, or load split depending on the parameter.

If multiple parameters change at once, the lap-time delta is harder to explain.

## Sensitivity signs
Some parameter changes have expected directions.

Examples:

- Higher `base_mu` should usually improve grip-limited behaviour.
- Higher `cog_z` should not make rollover-limited cornering look better.
- Higher drag should usually hurt acceleration or top speed.
- More downforce can help corners but may hurt straights through drag tradeoff.

Unexpected signs do not automatically mean the code is wrong, but they require diagnostics.

## Stale parameters
A stale parameter is one that appears to change but does not affect outputs.

That can happen when:

- the parameter is not wired into the active model path,
- the selected model variant ignores it,
- another cap dominates the output,
- the test track does not excite the relevant physics.

Use sensitivity sweeps and limiter diagnostics together.
A zero lap-time delta is not enough evidence by itself.

## A/B workflow
Use A/B sweeps for controlled comparisons.

Useful path:

- [src/ab_testing/run_ab_suite.py](../../src/ab_testing/run_ab_suite.py)

Inspect:

- `ab_summary.md`,
- `ab_runs.csv`,
- `ab_sensitivity.csv`,
- limiter counts,
- fallback and solver gates,
- normal-load gates,
- scenario context fields.

Milestone 3 includes a non-trivial `base_mu` sensitivity gate and a `cog_z` sign check.
The A/B runner also accepts `--stale-threshold`, which marks parameter effects as stale when the lap-time delta is too small to be meaningful.
For senior review, always pair A/B sweep results with diagnostics such as limiter mode mix, solver health, fallback rate, normal-load events, and tyre out-of-domain count.

## How to debug a surprising result
Use this order:

1. Check static docs and code path so the parameter is supposed to be active.
2. Check limiter mode mix to see what subsystem controls the lap.
3. Check solver health and fallback rate.
4. Check normal-load and tyre-domain diagnostics.
5. Check GG envelope shape and g-channel spikes.
6. Only then consider changing calibration values.

## Do not tune scenarios into the vehicle
Scenario effects such as wet track grip or air-density changes should not mutate base vehicle truths.
Use explicit scenario multipliers instead.

See [Scenario Separation](Scenario-Separation.md).

## Assumptions and limits
- A/B sensitivity is only meaningful when the solver health is acceptable.
- A lap-time delta can be real but still caused by an unintended limiter change.
- Parameter calibration should be checked against real data when available.
- Some parameters need specific synthetic maneuvers before full-lap tests are informative.

## Verification checks
Useful commands:

```bash
uv run python src/ab_testing/run_ab_suite.py --tracks FSUK,SkidpadF26,StraightLineTrack --variants baseline --output-dir ab_test_outputs/sensitivity_check --fallback-threshold 0.15 --stale-threshold 0.05 --max-out-of-domain-count 130000 --enforce-milestone3-gates --enforce-milestone4-gates
uv run python src/diagnostics/constant_radius_suite.py --output-dir artifacts/constant_radius_sensitivity
```

## Next lesson
- [Scenario Separation](Scenario-Separation.md)

## Related lessons
- [Validation and Falsification Workflow](Validation-and-Falsification-Workflow.md)
- [Vehicle Modelling Diagnostics and Trust Checks](Vehicle-Modelling-Diagnostics.md)
- [Vehicle Analysis IRL vs Simulator and GG Envelope](Vehicle-Analysis-IRL-vs-Simulator.md)
- [Load Transfer and Normal Loads](Load-Transfer-and-Normal-Loads.md)
- [Lessons Index](README.md)
