# First-Principles Migration Checklist

Purpose: move the simulator toward first-principles realism with strict, falsifiable gates.

How to use this document:
- Treat each milestone as a release gate.
- Do not start the next milestone until current gates pass.
- Keep one frozen baseline config for all comparisons.

---

## Milestone 0: Freeze Baseline and Reproducibility

### Objective
Lock current behavior so future changes are measured against a stable reference.

### Required artifacts
- FSUK full-lap run outputs
- SkidpadF26 full-lap run outputs
- StraightLineTrack full-lap run outputs
- Current diagnostics bundle under artifacts/

### Required metrics to record
- Lap time (s)
- Max absolute lateral acceleration (g)
- Max combined acceleration (g_total)
- Corner fallback rate
- Corner solver success rate

### Pass gates
- Re-run drift for lap time on each track is <= 0.25%.
- Re-run drift for max |g_lat| on each track is <= 3%.
- Re-run drift for max g_total on each track is <= 3%.
- Existing tyre invariant tests pass.

---

## Milestone 1: Governing Equations and Units Audit

### Objective
Ensure every core dynamics equation is dimensionally and sign-consistent.

### Scope
- Lateral force balance
- Longitudinal force balance
- Yaw moment balance
- Load transfer terms
- Rollover bound

### Required checks
- Units for every term are documented and validated.
- Limiting-case tests exist for:
  - zero curvature
  - zero speed
  - zero throttle
  - zero brake
- No unexplained constants in critical force/balance equations.

### Pass gates
- Unit-consistency tests: 100% pass.
- Limiting-case tests: 100% pass.
- Corner-equilibrium residual telemetry channels exist and are finite for solved points.
- Strict magic-constant scan passes for core solver files.
- Equation audit signed off in docs.

### Verification run (single flow)

```bash
uv run python -m unittest tests.test_limiting_case_contracts -v
uv run python tools/analysis/m1_magic_constant_scan.py --strict
```

---

## Milestone 2: Tyre Model Validity Envelope

### Objective
Guarantee tyre force usage stays inside validated domain, or is explicitly bounded.

### Scope
- Lateral force path
- Longitudinal force path
- Combined-slip budgeting
- High-load behavior

### Required checks
- Valid load and slip domains are declared.
- Out-of-domain force lookup is clamped or flagged.
- Combined-slip budget is consistent across corner solve, forward pass, backward pass.

### Pass gates
- Tyre invariants: PASS.
- Lateral RMSE <= 12% against verification dataset.
- Longitudinal RMSE <= 12% against verification dataset.
- High-load growth gate for clamped variant <= 1.05.
- Out-of-domain usage count is reported in diagnostics.
- Baseline hard gate passes with `tyre_out_of_domain_total <= 130000` for standard-track baseline A/B run.

### Verification run (recommended)

```bash
uv run python -m unittest tests.test_tyre_force_contracts tests.test_tyre_peak_load_clamp_contracts tests.test_tyre_validity_domain_contracts -v
uv run python -m unittest tests.test_limiting_case_contracts -v
uv run python tools/analysis/compare_tyre_model.py --validate --model-variant tyre_peak_load_clamp --rmse-threshold-pct 12 --max-high-load-growth-ratio 1.05 --max-out-of-domain-count -1
uv run python src/ab_testing/run_ab_suite.py --tracks StraightLineTrack --variants baseline --output-dir ab_test_outputs/m2_domain_smoke --fallback-threshold 0.15 --stale-threshold 0.05 --max-out-of-domain-count -1
```

Strict gate check (measured baseline threshold):

```bash
uv run python src/ab_testing/run_ab_suite.py --tracks FSUK,SkidpadF26,StraightLineTrack --variants baseline --output-dir ab_test_outputs/m2_domain_hard_gate --fallback-threshold 0.15 --stale-threshold 0.05 --max-out-of-domain-count 130000
uv run python tools/analysis/compare_tyre_model.py --validate --model-variant tyre_peak_load_clamp --rmse-threshold-pct 12 --max-high-load-growth-ratio 1.05 --max-out-of-domain-count -1
```

---

## Milestone 3: Load Transfer and Aero Coupling

### Objective
Make normal-load evolution emerge from geometry and force balance, not tuning shortcuts.

### Scope
- Longitudinal transfer
- Lateral transfer proxy
- Aero downforce and drag consistency

### Required checks
- Front/rear normal-load paths are explicit and shared across solver stages.
- Normal loads remain non-negative.
- Speed-dependent aero terms are used consistently.

### Pass gates
- Non-physical normal-load events: zero.
- Sensitivity sign checks pass (for example, higher cog_z should not increase cornering realism metrics).
- Base tyre grip parameter produces non-trivial constant-radius sensitivity:
  - |delta lap time| > 0.001 s in contract test.

### Verification run (strict)

```bash
uv run python -m unittest tests.test_limiting_case_contracts -v
uv run python src/ab_testing/run_ab_suite.py --tracks FSUK,SkidpadF26,StraightLineTrack --variants baseline --output-dir ab_test_outputs/m3_hard_gate --fallback-threshold 0.15 --stale-threshold 0.05 --max-out-of-domain-count 130000 --enforce-milestone3-gates
```

Notes:
- Milestone 3 A/B gate checks enforce:
  - zero non-physical normal-load events in runtime diagnostics,
  - `cog_z` sign check on curved tracks (higher `cog_z` must not reduce lap time),
  - non-trivial `base_mu` sensitivity on representative curved track FSUK (|delta lap time| > 0.001 s).

---

## Milestone 4: Numerical Robustness Without Physics Leakage

### Objective
Improve convergence reliability while keeping fallback physically constrained.

### Scope
- Retry tiers
- Bounded fallback
- Per-point limiter attribution

### Required checks
- Retry tiers are used only for numerical convergence, not extra performance.
- Fallback speed is bounded by physical caps and continuity cap.
- Limiter source is recorded per point (rollover, tyre lateral, combined budget, power, braking, straight cap).

### Pass gates
- Fallback rate on FSUK <= 0.15.
- Fallback rate on SkidpadF26 <= 0.15.
- Fallback rate on StraightLineTrack <= 0.05.
- Solver success rate on each track >= 0.85.
- No discontinuous g spikes attributable to fallback.

### Verification run (strict)

```bash
uv run python src/ab_testing/run_ab_suite.py --tracks FSUK,SkidpadF26,StraightLineTrack --variants baseline --output-dir ab_test_outputs/m4_hard_gate --fallback-threshold 0.15 --stale-threshold 0.05 --max-out-of-domain-count 130000 --enforce-milestone4-gates
```

Notes:
- `--enforce-milestone4-gates` applies track-specific hard gates:
  - fallback rate: FSUK <= 0.15, SkidpadF26 <= 0.15, StraightLineTrack <= 0.05
  - solver success rate: FSUK >= 0.85, SkidpadF26 >= 0.85, StraightLineTrack >= 0.95

---

## Milestone 5: Validation Hierarchy and Falsification

### Objective
Prove model credibility layer-by-layer and catch wrong physics quickly.

### Required validation layers
- Layer A: component contracts (tyre, solver equations, force bounds).
- Layer B: synthetic maneuvers (constant-radius, straight-line accel/brake).
- Layer C: full-lap realism diagnostics (G-G-V envelope, lap-time plausibility).

### Required falsification tests
- At least one falsification test per subsystem where expected result is known.
- Failures should localize to one layer without ambiguity.

### Pass gates
- All Layer A tests pass.
- All Layer B tests pass.
- Layer C realism gates pass:
  - FSUK peak |g_lat| <= 2.0 g (caution threshold)
  - FSUK peak g_total <= 4.45 g (calibrated hard gate; 3.0 g remains caution threshold)
  - G-G-V cloud shape remains plausible and bounded by declared assumptions.

### Verification run (strict)

```bash
uv run python -m unittest tests.test_tyre_force_contracts tests.test_tyre_peak_load_clamp_contracts tests.test_tyre_validity_domain_contracts tests.test_solver_contracts tests.test_limiting_case_contracts tests.test_falsification_and_scenario_contracts -v
uv run python src/ab_testing/run_ab_suite.py --tracks FSUK,SkidpadF26,StraightLineTrack --variants baseline --output-dir ab_test_outputs/m5_hard_gate --fallback-threshold 0.15 --stale-threshold 0.05 --max-out-of-domain-count 130000 --enforce-milestone3-gates --enforce-milestone4-gates --enforce-milestone5-gates --m5-max-abs-glat-g 2.0 --m5-max-gtotal-g 4.45
```

Notes:
- `--enforce-milestone5-gates` enforces FSUK Layer C realism limits in A/B output:
  - peak `|g_lat| <= 2.0` g
  - peak `g_total <= 4.45` g

---

## Milestone 6: Scenario Separation (After Core Physics)

### Objective
Separate scenario effects from base vehicle physics cleanly.

### Scope
- Vehicle baseline parameters remain fixed truths.
- Scenario terms (track condition, weather) are separate multipliers/settings.

### Required checks
- Changing scenario does not require retuning base vehicle parameters.
- A/B reports include scenario context explicitly.

### Pass gates
- Baseline vehicle calibration remains stable across scenario variants.
- Scenario-only changes produce directionally expected shifts without violating Milestone 5 realism gates.

### Verification run (strict)

```bash
uv run python -m unittest tests.test_falsification_and_scenario_contracts -v
uv run python src/ab_testing/run_ab_suite.py --tracks FSUK,SkidpadF26,StraightLineTrack --variants baseline --output-dir ab_test_outputs/m6_hard_gate --fallback-threshold 0.15 --stale-threshold 0.05 --max-out-of-domain-count 130000 --enforce-milestone3-gates --enforce-milestone4-gates --enforce-milestone5-gates --enforce-milestone6-gates --scenario-name baseline --scenario-grip-scale 1.0 --scenario-air-density-scale 1.0 --m5-max-abs-glat-g 2.0 --m5-max-gtotal-g 4.45
uv run python src/ab_testing/run_ab_suite.py --tracks FSUK,SkidpadF26,StraightLineTrack --variants baseline --output-dir ab_test_outputs/m6_wet_scenario --fallback-threshold 0.15 --stale-threshold 0.05 --max-out-of-domain-count -1 --enforce-milestone3-gates --enforce-milestone4-gates --enforce-milestone5-gates --enforce-milestone6-gates --scenario-name wet_track --scenario-grip-scale 0.9 --scenario-air-density-scale 1.03 --m5-max-abs-glat-g 2.0 --m5-max-gtotal-g 4.45
```

Notes:
- Scenario effects are injected only through `scenario` multipliers (`grip_scale`, `air_density_scale`), not by retuning base vehicle parameters.
- A/B outputs now include explicit scenario context fields.

---

## Suggested Execution Order

1. Milestone 1 (equations and units)
2. Milestone 4 (limiter attribution and robust bounded solve diagnostics)
3. Milestone 3 (load transfer and aero coupling cleanup)
4. Milestone 5 (falsification-first validation hierarchy)
5. Milestone 6 (scenario separation)

This order keeps the model physically interpretable first, then adds controlled scenario flexibility.

---

## Companion Roadmap

For parameter-by-parameter enforcement, debugging, and fix workflow, use:

- `docs/PARAMETER_ENFORCEMENT_AUDIT_ROADMAP.md`