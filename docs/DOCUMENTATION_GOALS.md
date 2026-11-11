# Simulator Documentation Goals

Purpose: define what "complete documentation" means for the simulator and provide stable gates for iterative documentation work.

## Overarching Goal

The simulator documentation should let a reader understand the model from first principles, map each idea to the implementation, and judge whether a result is physically credible.

The docs should support two audiences:

- Junior engineers who may not yet know vehicle dynamics or the codebase.
- Senior engineers who want to inspect assumptions, equations, failure modes, and validation gates.

The DeepSeek-backed chat assistant should be able to answer most simulator questions by retrieving the relevant documentation and giving grounded answers without inventing unsupported behavior.

## Completion Gates

The documentation is considered complete when all of these gates pass:

- Every core subsystem has a first-principles lesson page.
- Every lesson is linked from `docs/lessons/README.md`.
- Every lesson appears in `docs/lessons/index.json`.
- Every lesson explains the physical idea before the code path.
- Every subsystem page includes assumptions, limits, diagnostics, and validation checks.
- The eval question bank has source coverage for every required question.
- Chat answers meet the configured concept, source, and hallucination gates.

## Required Lesson Coverage

These first-principles pages form the expected complete lesson set:

- `Simulator-Basics.md`
- `Tyre-Model.md`
- `Tyre-Model-Deep-Dive.md`
- `Powertrain-Model.md`
- `Aero-Model.md`
- `Load-Transfer-and-Normal-Loads.md`
- `Braking-Dynamics-and-Deceleration-Budget.md`
- `Vehicle-Modelling.md`
- `simulator-summary.md`
- `Numerical-Robustness-and-Solver-Failure-Modes.md`
- `Vehicle-Modelling-Diagnostics.md`
- `Vehicle-Analysis-IRL-vs-Simulator.md`
- `Track-Geometry-and-Sampling.md`
- `Validation-and-Falsification-Workflow.md`
- `Calibration-and-Sensitivity-Workflow.md`
- `Scenario-Separation.md`

## Standard Lesson Pattern

Each first-principles lesson should normally include:

- `Read this after`
- `Goal`
- A one minute mental model or equivalent plain-English overview.
- First-principles explanation of the physics or numerical method.
- Runtime implementation path with code references.
- Diagnostics or output channels to inspect.
- Assumptions and limits.
- Verification or validation commands where applicable.
- `Next lesson`
- `Related lessons`

## Eval Pass Targets

Initial target:

- Static documentation checks: 100% pass.
- Question source coverage: 100% pass for required questions.
- Chat concept score: at least 85%.
- Chat source score: at least 85%.
- Critical unsupported-claim findings: zero.

Tightened target after the first full docs pass:

- Chat concept score: at least 90%.
- Chat source score: at least 90%.
- Senior-review questions: at least 90%.

## Iteration Loop

Use this loop until the gates pass:

1. Run static docs evals.
2. Run chat evals when `config/deepseek_key` is available.
3. Identify weak topics and missing source coverage.
4. Patch the relevant docs.
5. Rebuild `docs/lessons/index.json`.
6. Re-run evals.

The loop should have explicit stop conditions when automated:

- maximum iteration count,
- maximum API spend,
- no critical failures remaining,
- configured pass thresholds met.
