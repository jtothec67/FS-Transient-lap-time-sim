# Validation and Falsification Workflow

## Read this after
Read [Vehicle Modelling Diagnostics and Trust Checks](Vehicle-Modelling-Diagnostics.md) first.

## Goal
Explain how to test the simulator layer by layer, how to use falsification cases, and how to avoid trusting plausible-looking but unsupported outputs.

## One minute mental model
Validation is not one big test at the end.
It is a hierarchy.

Small tests prove local contracts.
Synthetic scenarios prove known behaviours.
Full-lap diagnostics check whether the combined result remains plausible.

Falsification is the habit of asking, "What input should break or expose this assumption?"

## Layer A component contracts
Layer A checks small pieces with known behaviour.

Examples:

- tyre force invariants,
- valid tyre load and slip domains,
- solver limiting cases,
- parameter enforcement,
- basic force bounds.

Useful tests:

- [tests/test_tyre_force_contracts.py](../../tests/test_tyre_force_contracts.py)
- [tests/test_tyre_peak_load_clamp_contracts.py](../../tests/test_tyre_peak_load_clamp_contracts.py)
- [tests/test_tyre_validity_domain_contracts.py](../../tests/test_tyre_validity_domain_contracts.py)
- [tests/test_solver_contracts.py](../../tests/test_solver_contracts.py)
- [tests/test_limiting_case_contracts.py](../../tests/test_limiting_case_contracts.py)

Layer A failures should localize to one subsystem.

## Layer B synthetic maneuvers
Layer B uses simple maneuvers where the expected direction is known.

Examples:

- straight-line acceleration,
- straight-line braking,
- constant-radius cornering,
- skidpad-style tracks,
- degenerate track segment falsification.

Useful paths:

- [tools/sweeps/straight_line_test.py](../../tools/sweeps/straight_line_test.py)
- [tools/sweeps/lift_coast_test.py](../../tools/sweeps/lift_coast_test.py)
- [src/diagnostics/constant_radius_suite.py](../../src/diagnostics/constant_radius_suite.py)
- [tests/test_falsification_and_scenario_contracts.py](../../tests/test_falsification_and_scenario_contracts.py)

Layer B catches wrong signs and stale parameters faster than a full lap.

## Layer C full-lap realism
Layer C checks the combined system on representative tracks.

Important outputs:

- lap time,
- peak lateral g,
- peak total g,
- fallback rate,
- solver success rate,
- tyre out-of-domain count,
- normal-load non-physical events,
- limiter mode mix,
- GG envelope shape.

Useful path:

- [src/ab_testing/run_ab_suite.py](../../src/ab_testing/run_ab_suite.py)

Full-lap gates should not replace component tests.
They prove integration credibility, not every internal mechanism.

## Falsification examples
A good falsification case has a known expected outcome.

Examples already present:

- invalid corner-solver upper bound should fail with `invalid_speed_bound`,
- repeated-distance track segment should be marked `degenerate_segment`,
- scenario changes should not mutate base vehicle parameters.

These tests live in [tests/test_falsification_and_scenario_contracts.py](../../tests/test_falsification_and_scenario_contracts.py).

## Documentation and chat evals
The documentation eval harness is another validation layer.
It checks whether a reader or chat assistant can answer simulator questions from the docs.

Useful files:

- [docs/DOCUMENTATION_GOALS.md](../DOCUMENTATION_GOALS.md)
- [docs/evals/simulator_qa.jsonl](../evals/simulator_qa.jsonl)
- [tools/evals/run_docs_eval.py](../../tools/evals/run_docs_eval.py)

If DeepSeek gives a confident but wrong answer, inspect:

- which lesson sections were retrieved,
- whether the question has a real source page,
- whether the source page explains the concept directly,
- whether the lesson index is stale,
- whether the answer made an unsupported inference.

Documentation readiness requires these gates:

- all required pages exist,
- static documentation checks pass,
- QA evals pass,
- answers cite or retrieve grounded sources,
- critical hallucinations or unsupported simulator claims are zero.

## Standard hard-gate command
The broad Milestone 5 style run is:

```bash
uv run python -m unittest tests.test_tyre_force_contracts tests.test_tyre_peak_load_clamp_contracts tests.test_tyre_validity_domain_contracts tests.test_solver_contracts tests.test_limiting_case_contracts tests.test_falsification_and_scenario_contracts -v
uv run python src/ab_testing/run_ab_suite.py --tracks FSUK,SkidpadF26,StraightLineTrack --variants baseline --output-dir ab_test_outputs/m5_hard_gate --fallback-threshold 0.15 --stale-threshold 0.05 --max-out-of-domain-count 130000 --enforce-milestone3-gates --enforce-milestone4-gates --enforce-milestone5-gates --m5-max-abs-glat-g 2.0 --m5-max-gtotal-g 4.45
```

## Assumptions and limits
- Passing gates does not prove the model is universally correct.
- Gates only cover declared assumptions and representative scenarios.
- Real test data remains the best external check.
- When a full-lap gate fails, debug down the hierarchy rather than tuning blindly.

## Next lesson
- [Calibration and Sensitivity Workflow](Calibration-and-Sensitivity-Workflow.md)

## Related lessons
- [Vehicle Modelling Diagnostics and Trust Checks](Vehicle-Modelling-Diagnostics.md)
- [Vehicle Analysis IRL vs Simulator and GG Envelope](Vehicle-Analysis-IRL-vs-Simulator.md)
- [Track Geometry and Sampling for Vehicle Dynamics](Track-Geometry-and-Sampling.md)
- [Scenario Separation](Scenario-Separation.md)
- [Lessons Index](README.md)
