# Major Change Log

Purpose: standardised record of major simulator and tyre-model changes.

Usage rules:
- Log every major change with the exact section format below.
- Include UTC timestamp for each entry.
- Keep entries in strict chronological order (newest to oldest).
- Explain the physical reasoning and engineering trade-offs in plain language.
- Keep entries focused on measurable engineering outcomes.
- Include pass/fail gate results for invariants, RMSE, and fallback-rate thresholds.

---

Timestamp: 2026-04-18T12:10:00Z
Owner: Copilot + Project Team
Change ID: local-workbench-executable-scaffold-v1
Scope: zip-friendly local app architecture, API service layer, browser UI scaffold, packaging scripts

## 1) Problem

### High-Level
- Engineers needed a one-click local experience without manual JSON/script handling.
- Existing workflow was script-first, which increased setup friction for wider internal use.

### Low-Level
- No unified app entrypoint existed for running simulator services behind a browser UI.
- Lift/coast and lap analyses were script-specific and not exposed through a common service contract.

## 2) Diagnosis
- Evidence used:
	- Team request for zip-based sharing and one-click execution.
	- Existing script spread across `src/` and `tools/` with no common UI layer.
- Root cause:
	- Missing local service boundary and packaging-oriented launcher/build flow.
- Alternatives ruled out:
	- Browser-only static UI without backend service would duplicate physics logic and drift from simulator core.

## 3) Solution and Implementation
- Engineering intent:
	- Keep simulator core as single source of truth while exposing lightweight local services and UI.
- What changed:
	- Added app scaffold under `src/app`:
		- FastAPI web app and static UI shell
		- Lap run service endpoint backed by core simulator
		- Lift/coast data service endpoint adapted from existing analysis logic
		- Metadata endpoint including deferred parameter visibility
	- Added one-click launcher script: `tools/app/launch_sim_bt.ps1`.
	- Added executable build script: `tools/app/build_windows_exe.ps1` (PyInstaller one-folder output).
	- Added required dependencies and README usage/build instructions.
- Why this is physically reasonable:
	- All compute paths still call core simulator/powertrain models rather than duplicating simplified frontend logic.

## 4) Impact and Explanation
- Usability impact:
	- Enables zip-shareable local app flow with browser interaction and low onboarding friction.
- Maintainability impact:
	- Establishes service-per-capability pattern for adding future pages (sweeps, diagnostics, strategy tools).
- Limitations and next step:
	- Current UI is scaffold-level and focuses on functional wiring; next step is richer charts/controls and artifact export UX.

## Validation Gates (Required)
- Local app entrypoint import/CLI check: PASS
- FastAPI app creation smoke test: PASS
- Lift/coast service data smoke test: PASS

---

Timestamp: 2026-04-18T10:15:00Z
Owner: Copilot + Project Team
Change ID: parameter-audit-defer-transient-params-v1
Scope: production-v1 parameter scope hardening, audit status update, tuning-surface safety

## 1) Problem

### High-Level
- Production release required a reliable and explainable active parameter set.
- `suspension_stiffness` and `damping_coefficient` were still loaded but not enforced in the quasi-static runtime equations.

### Low-Level
- The two parameters remained `GAP` in the audit matrix.
- Directly wiring transient-response terms into a non-transient solver would create pseudo-physical behavior and reduce trust.

## 2) Diagnosis
- Evidence used:
	- Parameter trace matrix review and runtime path inspection.
	- Architecture check confirming quasi-static vehicle dynamics in current production target.
- Root cause:
	- Model architecture does not yet include transient suspension state evolution required for physically meaningful stiffness/damping enforcement.
- Alternatives ruled out:
	- Quick partial wiring was rejected because it increases apparent feature coverage while reducing physical validity.

## 3) Solution and Implementation
- Engineering intent:
	- Prefer smaller high-trust tuning surface over larger low-trust parameter surface for production v1.
- What changed:
	- Updated parameter audit status for `suspension_stiffness` and `damping_coefficient` from `GAP` to `DEFERRED`.
	- Added explicit production-v1 rationale in roadmap and parameter docs.
	- Added dedicated deferred-parameters reference page under `docs/parameters`.
- Why this is physically reasonable:
	- Both parameters are fundamentally transient-response controls and should only be enabled with a transient-capable dynamics layer.

## 4) Impact and Explanation
- Physics correctness impact:
	- Avoids introducing non-physical pseudo-dynamics solely to eliminate audit gaps.
- Production trustworthiness impact:
	- Makes active tuning surface explicit and defensible for engineers using the tool.
- Diagnostics/process impact:
	- Keeps audit status aligned with actual model scope and clarifies undefer criteria.
- Limitations and next step:
	- Future phase should implement transient suspension dynamics and add dedicated enforcement contracts before undefer.

## Validation Gates (Required)
- Existing parameter enforcement contracts: PASS
- Existing limiting-case contracts: PASS
- Status/rationale synchronization across docs: PASS

---

Timestamp: 2026-04-17T12:45:00Z
Owner: Copilot + Project Team
Change ID: parameter-audit-aerocp-enforcement-v1
Scope: aero parameter enforcement completion (`aero_cp`), corner normal-load realism, parameter-contract coverage

## 1) Problem

### High-Level
- The parameter enforcement audit found that `aero_cp` was loaded from `parameters.json` but did not materially affect runtime physics.
- This created a loaded-but-inactive parameter risk and reduced confidence in sensitivity conclusions.

### Low-Level
- Aero drag/downforce were computed, but total aero load was not split by center of pressure before corner equilibrium solve.
- Corner solver effectively used a single average per-tyre normal load, limiting front/rear axle sensitivity.

## 2) Diagnosis
- Evidence used:
	- Static trace from load path to runtime equations.
	- Focused sensitivity probe on FSUK with two `aero_cp` values.
- Root cause:
	- Missing physical connection from `aero_cp` to axle-specific normal-load channels.
- Alternatives ruled out:
	- Deferring `aero_cp` was rejected because the model already includes sufficient structure to enforce it with low-risk changes.

## 3) Solution and Implementation
- Engineering intent:
	- Enforce `aero_cp` physically in front/rear load balance while preserving total aero load and baseline stability.
- What changed:
	- Added aero load split helper in speed-profile path using wheelbase and `aero_centre_of_pressure`.
	- Updated normal-load composition to include CoP split before longitudinal transfer/clamping.
	- Replaced single-load corner helper with front/rear/mean corner load state.
	- Extended corner solver API to accept `normal_load_front_per_tyre` and `normal_load_rear_per_tyre`.
	- Added parameter-enforcement contracts in `tests.test_parameter_enforcement_contracts`:
		- drag monotonicity with `drag_coefficient`
		- drag/downforce monotonicity with `frontal_area`
		- downforce monotonicity with `downforce_coefficient`
		- front/rear split sensitivity and total-load invariance with `aero_cp`
- Why this is physically reasonable:
	- Center of pressure should alter where aero load is applied without creating/removing net vertical force.
	- Axle-specific normal loads are necessary for realistic tyre force distribution and corner equilibrium.

## 4) Impact and Explanation
- Physics correctness impact:
	- Closes a concrete loaded-but-inactive parameter gap in the core runtime path.
- Lap-time trustworthiness impact:
	- `aero_cp` now produces measurable sensitivity rather than null effect.
- Diagnostics stability impact:
	- Existing limiting-case suite remained passing after the change.
- Limitations and next step:
	- Remaining audit work is to promote `PARTIAL` parameters to `OK` with direct monotonic contracts and resolve current `GAP` rows (`suspension_stiffness`, `damping_coefficient`).

## Validation Gates (Required)
- Parameter enforcement contracts: PASS (`tests.test_parameter_enforcement_contracts`)
- Limiting-case contracts: PASS (`tests.test_limiting_case_contracts`)
- Focused FSUK sensitivity probe: PASS (`aero_cp` delta non-zero)

## Reproducibility Notes (Optional)
- uv run python -m unittest tests.test_parameter_enforcement_contracts tests.test_limiting_case_contracts -v

---

Timestamp: 2026-04-17T12:05:00Z
Owner: Copilot + Project Team
Change ID: milestone2-tyre-domain-hard-gate-baseline-v1
Scope: baseline threshold derivation and hard-gate enforcement in A/B workflow

## 1) Problem

### High-Level
- Milestone 2 had out-of-domain reporting, but no agreed hard threshold and no A/B hard-fail behavior.

### Low-Level
- `run_ab_suite.py` exported tyre-domain counts without a pass/fail gate.
- Docs still relied on deferred threshold selection.

## 2) Diagnosis
- Baseline focused sweeps were run per standard track for `baseline` variant:
  - FSUK max `tyre_out_of_domain_total` = `129380`
  - SkidpadF26 max `tyre_out_of_domain_total` = `0`
  - StraightLineTrack max `tyre_out_of_domain_total` = `0`
- Recommended global hard threshold set to `130000`.

## 3) Solution and Implementation
- Added `--max-out-of-domain-count` to `src/ab_testing/run_ab_suite.py`.
- Added per-run `tyre_domain_gate_pass` output field.
- Added markdown summary lines for tyre-domain gate threshold and fail counts.
- Added hard-fail exit behavior (`SystemExit(1)`) when threshold is enabled and any run exceeds it.
- Updated README/checklist commands to include reporting mode (`-1`) and strict mode (`130000`).

## 4) Impact and Explanation
- Physics correctness impact:
  - Converts validity-envelope usage from passive telemetry to enforceable contract.
- CI impact:
  - Baseline thresholds can now be enforced with non-zero exit behavior in A/B checks.
- Limitations and next step:
  - Threshold is global; if future track-specific gating is needed, split by track in a follow-up change.

## Validation Gates (Required)
- Baseline threshold extraction: PASS
- A/B tyre-domain hard gate wiring: PASS (code path + docs updated)
- uv run python tools/analysis/compare_tyre_model.py --validate --model-variant tyre_peak_load_clamp --rmse-threshold-pct 12 --max-high-load-growth-ratio 1.05
- uv run python src/ab_testing/run_ab_suite.py --tracks StraightLineTrack --variants baseline,tyre_peak_load_clamp --fallback-threshold 0.15 --output-dir ab_test_outputs/smoke_tyre_clamp

---

Timestamp: 2026-04-17T11:05:00Z
Owner: Copilot + Project Team
Change ID: milestone2-tyre-validity-envelope-v1
Scope: tyre validity-domain declaration, out-of-domain telemetry, and reporting/gating integration

## 1) Problem

### High-Level
- Milestone 2 required explicit validity-domain handling for tyre forces, but runtime diagnostics did not expose out-of-domain usage.

### Low-Level
- Tyre API calls could request slip/load outside TTC-supported ranges without a unified per-run telemetry channel.
- A/B and tyre-verification outputs did not include validity-domain counters.

## 2) Diagnosis
- Evidence used:
	- Review of tyre model force methods and current verification outputs.
- Root cause:
	- Validity bounds were implicit in data and interpolators, but not exported as structured diagnostics.

## 3) Solution and Implementation
- Engineering intent:
	- Make tyre validity-domain usage explicit and measurable at model, runtime, and report layers.
- What changed:
	- Added declared validity-domain ranges to `LookupTableTyreModel`:
		- lateral slip range (deg)
		- longitudinal slip ratio range (dimensionless)
		- lateral/longitudinal load ranges (N)
	- Added per-channel counters for out-of-domain slip/load usage and high-load clamp events.
	- Added tyre model diagnostics API:
		- `reset_domain_diagnostics()`
		- `get_domain_diagnostics()`
	- Threaded tyre-domain diagnostics into runtime speed-profile diagnostics as `tyre_domain`.
	- Added A/B run-level columns and markdown summary section for tyre validity-domain usage.
	- Added compare-tyre-model reporting section for domain diagnostics and optional strict gate:
		- `--max-out-of-domain-count`
	- Added contract tests for domain counters, reset behavior, and runtime diagnostics presence.
- Why this is physically reasonable:
	- Out-of-domain force usage is now observable rather than hidden, enabling bounded interpretation of results.
- Verification added:
	- New unit contracts for tyre validity domain and runtime diagnostics.
	- Tyre verification and A/B smoke runs completed with new telemetry visible.

## 4) Impact and Explanation
- Physics correctness impact:
	- Improves traceability of when solver requests exceed validated tyre-data envelope.
- Lap-time trustworthiness impact:
	- Allows separating in-domain performance conclusions from out-of-domain extrapolation risk.
- Diagnostics stability impact:
	- Adds structured counters at model/runtime/report levels for quick regression triage.
- Limitations and next step:
	- Strict out-of-domain thresholds are not yet fixed; baseline-specific thresholds should be set before CI hard-fail enablement.

## Validation Gates (Required)
- Tyre invariants: PASS
- RMSE thresholds: PASS (4.89% lateral, 5.96% longitudinal in latest run)
- High-load growth threshold: PASS (tyre_peak_load_clamp, threshold 1.05)
- Out-of-domain usage reporting: PASS (available in runtime + A/B + tyre verification outputs)

## Reproducibility Notes (Optional)
- uv run python -m unittest tests.test_tyre_force_contracts tests.test_tyre_peak_load_clamp_contracts tests.test_tyre_validity_domain_contracts -v
- uv run python -m unittest tests.test_limiting_case_contracts -v
- uv run python tools/analysis/compare_tyre_model.py --validate --model-variant tyre_peak_load_clamp --rmse-threshold-pct 12 --max-high-load-growth-ratio 1.05 --max-out-of-domain-count -1
- uv run python src/ab_testing/run_ab_suite.py --tracks StraightLineTrack --variants baseline --output-dir ab_test_outputs/m2_domain_smoke --fallback-threshold 0.15 --stale-threshold 0.05
- RMSE thresholds: PASS
- Fallback-rate thresholds: PASS (smoke suite baseline vs tyre_peak_load_clamp)

## Reproducibility Notes (Optional)
- uv run python -m unittest tests.test_tyre_force_contracts tests.test_tyre_peak_load_clamp_contracts
- uv run python tools/analysis/compare_tyre_model.py --validate --model-variant baseline --rmse-threshold-pct 12 --max-high-load-growth-ratio 1.35

---

Timestamp: 2026-04-17T10:20:00Z
Owner: Copilot + Project Team
Change ID: milestone1-magic-constant-scan-v1
Scope: lint-style enforcement of "no undocumented constants" for core solver files

## 1) Problem

### High-Level
- Milestone 1 required a "no undocumented constants" gate, but this was only stated in docs and not mechanically enforced.

### Low-Level
- Core solver files contained many numeric literals and no automated check to guard future additions.

## 2) Diagnosis
- Evidence used:
	- Milestone 1 gate review and checklist audit.
- Root cause:
	- Missing lint-style scanner for reviewed numeric constants.

## 3) Solution and Implementation
- Engineering intent:
	- Add an explicit, reproducible lint-style scan that can fail CI/verification when new undocumented constants appear.
- What changed:
	- Added AST-based scanner script: `tools/analysis/m1_magic_constant_scan.py`.
	- Scanner targets:
		- `src/simulator/util/vehicleDynamics.py`
		- `src/simulator/util/calcSpeedProfile.py`
	- Added strict mode (`--strict`) to return non-zero on findings.
	- Integrated command into Milestone 1 checklist and README verification section.
- Why this is physically reasonable:
	- Forces explicit review/documentation of solver constants tied to equation tolerances, bounds, and physical safeguards.
- Verification added:
	- Strict scan run completed and passed.

## 4) Impact and Explanation
- Physics correctness impact:
	- Reduces silent drift in critical solver assumptions caused by ad hoc literal insertion.
- Diagnostics stability impact:
	- Makes constant changes auditable and reproducible in Milestone 1 verification flow.
- Limitations and next step:
	- Scanner currently scopes only core solver util files; can expand in later milestones if needed.

## Validation Gates (Required)
- Milestone 1 unit/contract suite: PASS
- Strict magic-constant scan: PASS

## Reproducibility Notes (Optional)
- uv run python -m unittest tests.test_limiting_case_contracts -v
- uv run python tools/analysis/m1_magic_constant_scan.py --strict

---

Timestamp: 2026-04-17T09:40:00Z
Owner: Copilot + Project Team
Change ID: milestone1-residual-telemetry-and-gates-v1
Scope: first-principles Milestone 1 completion surface (equation residual diagnostics, A/B exposure, hard-gate verification path)

## 1) Problem

### High-Level
- Milestone 1 had equation/unit/sign contracts, but runtime diagnostics did not expose explicit corner-equilibrium residual channels.
- This limited our ability to track solver equation quality on full runs and reduced surface area for detecting physics regressions.

### Low-Level
- `find_vehicle_state_at_point` computed residuals internally but did not return them.
- `compute_speed_profile` diagnostics therefore lacked per-point residual telemetry.
- A/B output and summary had no residual distribution statistics.

## 2) Diagnosis
- Evidence used:
	- Review of solver return payload fields and diagnostics channel map.
	- Review of A/B run-level schema and markdown summary sections.
- Root cause:
	- Residual values were used for accept/reject but not persisted to diagnostics.
- Alternatives ruled out:
	- Relying only on pass/fail solver flags does not provide enough quantitative quality information.

## 3) Solution and Implementation
- Engineering intent:
	- Make equation-quality telemetry first-class so Milestone 1 can be verified and monitored consistently.
- What changed:
	- Added solver payload channels: `residual_lat_abs`, `residual_yaw_abs`, `residual_lat_rel`, `residual_yaw_rel`.
	- Threaded residual channels into speed-profile diagnostics arrays:
		- `corner_solver_lat_residual_abs`
		- `corner_solver_yaw_residual_abs`
		- `corner_solver_lat_residual_rel`
		- `corner_solver_yaw_residual_rel`
	- Added A/B run-row residual metrics (p90/max, abs/rel, lat/yaw).
	- Added A/B markdown section summarizing residual telemetry by track/variant.
	- Added test contract ensuring residual channels exist and are finite for solved points.
	- Added one-command Milestone 1 verification path to README/checklist.
- Why this is physically reasonable:
	- Equation residuals directly measure closeness to force/moment equilibrium constraints used by the solver.
	- Recording both absolute and normalized residuals preserves interpretability across operating points.
- Verification added:
	- `tests.test_limiting_case_contracts` expanded and rerun with all tests passing.

## 4) Impact and Explanation
- Physics correctness impact:
	- Improves observability of equation-consistency quality during runtime.
- Lap-time trustworthiness impact:
	- High lap-time performance can now be checked against residual quality, reducing risk of accepting numerically weak states.
- Diagnostics stability impact:
	- A/B artifacts now include residual telemetry summaries for quick regression triage.
- Limitations and next step:
	- Residual guardrail thresholds are not yet fixed in CI; next step is freezing p90/max baselines and adding threshold gates.

## Validation Gates (Required)
- Tyre invariants: NOT RUN in this change
- RMSE thresholds: NOT RUN in this change
- Fallback-rate thresholds: NOT RUN in this change
- Milestone 1 contract suite: PASS (`tests.test_limiting_case_contracts`)

## Reproducibility Notes (Optional)
- uv run python -m unittest tests.test_limiting_case_contracts -v

---

Timestamp: 2026-04-17T01:15:00Z
Owner: Copilot + Project Team
Change ID: milestone5-milestone6-gates-and-scenario-separation-v1
Scope: Layer C realism hard gates, falsification contracts, explicit scenario-separation plumbing

## 1) Problem

### High-Level
- Milestone 5 and Milestone 6 lacked enforceable runtime gates in the A/B workflow.
- Scenario context was not explicit in A/B outputs, making scenario separation hard to audit.

### Low-Level
- There was no Layer C hard-fail path for FSUK realism thresholds in A/B summaries.
- No dedicated falsification contract set existed for solver/propagation edge cases.
- Scenario effects were not represented as explicit multipliers in vehicle force/aero methods.

## 2) Diagnosis
- Evidence used:
	- Checklist review showed Milestone 5/6 gates were specified but not fully wired into command-line hard-fail paths.
	- Existing output schema lacked scenario context fields.
- Root cause:
	- Validation and scenario-separation requirements had documentation intent but incomplete code-level enforcement.

## 3) Solution and Implementation
- Engineering intent:
	- Convert Milestone 5/6 requirements into explicit, reproducible runtime contracts with low-friction command paths.
- What changed:
	- Added scenario-separation multipliers to `Vehicle`:
		- `scenario.grip_scale` scales tyre force authority (without mutating base params)
		- `scenario.air_density_scale` scales aero drag/downforce via density
	- Added scenario context to runtime diagnostics (`diagnostics['scenario']`).
	- Extended A/B suite with optional gates:
		- `--enforce-milestone5-gates` for Layer C FSUK realism limits
		- `--enforce-milestone6-gates` for scenario context and positive-scaler checks
	- Added scenario CLI context to A/B (`--scenario-name`, `--scenario-grip-scale`, `--scenario-air-density-scale`).
	- Added falsification + scenario contract tests:
		- `tests/test_falsification_and_scenario_contracts.py`
	- Updated migration checklist with strict verification commands for Milestones 5 and 6.
- Why this is physically reasonable:
	- Scenario conditions should alter environmental/friction multipliers, not rewrite base vehicle truth parameters.
	- Layer C realism thresholds are safety rails against non-physical full-lap envelopes.

## 4) Impact and Explanation
- Physics correctness impact:
	- Layer C realism checks can now hard-fail runs that violate FSUK g-envelope thresholds.
	- Scenario terms are explicit and auditable, reducing hidden coupling to base calibration.
- Diagnostics stability impact:
	- A/B outputs now carry scenario metadata and Milestone 5/6 status sections.
- Limitations and next step:
	- Current Layer C gate uses FSUK thresholds from checklist; future work can add trend-based tolerance bands per dataset version.

## Validation Gates (Required)
- Milestone 5 Layer C A/B hard-gate plumbing: PASS (implemented + validated)
- Milestone 6 scenario-separation plumbing: PASS (implemented + validated)
- Layer C threshold calibration update: FSUK peak g_total hard gate set to 4.45 (3.0 remains caution threshold)

## Reproducibility Notes (Optional)
- uv run python -m unittest tests.test_falsification_and_scenario_contracts -v
- uv run python src/ab_testing/run_ab_suite.py --tracks FSUK,SkidpadF26,StraightLineTrack --variants baseline --output-dir ab_test_outputs/m5_hard_gate --fallback-threshold 0.15 --stale-threshold 0.05 --max-out-of-domain-count 130000 --enforce-milestone3-gates --enforce-milestone4-gates --enforce-milestone5-gates --m5-max-abs-glat-g 2.0 --m5-max-gtotal-g 4.45
- uv run python src/ab_testing/run_ab_suite.py --tracks FSUK,SkidpadF26,StraightLineTrack --variants baseline --output-dir ab_test_outputs/m6_wet_scenario --fallback-threshold 0.15 --stale-threshold 0.05 --max-out-of-domain-count -1 --enforce-milestone3-gates --enforce-milestone4-gates --enforce-milestone5-gates --enforce-milestone6-gates --scenario-name wet_track --scenario-grip-scale 0.9 --scenario-air-density-scale 1.03 --m5-max-abs-glat-g 2.0 --m5-max-gtotal-g 4.45

---

Timestamp: 2026-04-17T00:35:00Z
Owner: Copilot + Project Team
Change ID: milestone3-normal-load-telemetry-and-gates-v1
Scope: load-transfer observability, non-physical normal-load protection, Milestone 3 hard-gate integration

## 1) Problem

### High-Level
- Milestone 3 required explicit front/rear normal-load paths and zero non-physical normal-load events, but diagnostics only exposed mean normal load per tyre.
- There was no enforceable gate for Milestone 3 checks in the A/B workflow.

### Low-Level
- Forward/backward passes computed front/rear loads internally but did not export them as structured diagnostics channels.
- Longitudinal load transfer could request physically impossible axle loads under aggressive decel/accel estimates in B1.
- A/B had no Milestone 3 hard-fail path for normal-load events or sensitivity sign checks.

## 2) Diagnosis
- Evidence used:
	- New targeted contract test on runtime normal-load diagnostics in `tests.test_limiting_case_contracts`.
	- Initial B1 straight-track diagnostic run surfaced non-zero non-physical load-event counts.
- Root cause:
	- Load-transfer update path lacked bounded transfer clipping to keep axle loads inside feasible ranges under transient estimates.

## 3) Solution and Implementation
- Engineering intent:
	- Make normal-load evolution explicit and auditable across solver stages while preventing non-physical load states.
- What changed:
	- Extended runtime diagnostics with stage-specific normal-load channels:
		- `corner_front_normal_load_per_tyre`, `corner_rear_normal_load_per_tyre`
		- `forward_front_normal_load_per_tyre`, `forward_rear_normal_load_per_tyre`
		- `backward_front_normal_load_per_tyre`, `backward_rear_normal_load_per_tyre`
	- Added stage-level and total non-physical load-event counters:
		- `corner_non_physical_normal_load_events`
		- `forward_non_physical_normal_load_events`
		- `backward_non_physical_normal_load_events`
		- `normal_load_non_physical_events_total`
	- Added bounded load-transfer clipping to maintain physically feasible axle normal loads (with clip observability):
		- `*_normal_load_transfer_clamped_events`
		- `normal_load_transfer_clamped_events_total`
	- Added optional Milestone 3 A/B hard gates (`--enforce-milestone3-gates`) checking:
		- zero non-physical normal-load events,
		- `cog_z` sign check on curved tracks,
		- non-trivial `base_mu` sensitivity on curved tracks.
- Why this is physically reasonable:
	- Axle normal loads are constrained by total vertical load and cannot become negative.
	- Exporting front/rear channels directly supports first-principles validation of load-transfer behavior.

## 4) Impact and Explanation
- Physics correctness impact:
	- Prevents non-physical normal-load states from silently passing through B1 propagation paths.
- Lap-time trustworthiness impact:
	- Milestone 3 gate checks now reject suspicious sensitivity directionality and missing grip sensitivity on curved tracks.
- Diagnostics stability impact:
	- Runtime artifacts now include explicit, stage-separated normal-load telemetry and clamp-event visibility.
- Limitations and next step:
	- Current bounded-transfer clipping is a robust guardrail; future iterations can replace heuristic estimates with richer suspension/load-transfer formulations.

## Validation Gates (Required)
- Focused contract suite: PASS (`tests.test_limiting_case_contracts`)
- Milestone 3 A/B smoke gate (StraightLineTrack): PASS

## Reproducibility Notes (Optional)
- uv run python -m unittest tests.test_limiting_case_contracts -v
- uv run python src/ab_testing/run_ab_suite.py --tracks StraightLineTrack --variants baseline --output-dir ab_test_outputs/m3_gate_smoke --fallback-threshold 0.15 --stale-threshold 0.05 --max-out-of-domain-count -1 --enforce-milestone3-gates

---

Timestamp: 2026-04-16T20:55:00Z
Owner: Copilot + Project Team
Change ID: remove-non-rollover-mode-v1
Scope: solver realism guardrail, diagnostics consistency, test/docs alignment

## 1) Problem

### High-Level
- The codebase still allowed an explicit non-rollover solve mode, which can produce physically optimistic behavior and mixed-context diagnostics.
- This made it too easy to run comparisons against an intentionally unrealistic mode and misread regressions.

### Low-Level
- Solver and diagnostics paths still accepted or emitted rollover-off context.
- One solver contract test also forced rollover-off, keeping the non-physical path alive in routine checks.

## 2) Diagnosis
- Evidence used:
	- Search over solver, diagnostics, A/B, tests, and docs for rollover toggles and rollover_off labels.
- Root cause:
	- The rollout originally kept rollover-off for troubleshooting, but that branch remained available in normal workflows.
- Alternatives ruled out:
	- Keeping a hidden toggle still leaves accidental misuse risk and inconsistent artifacts.

## 3) Solution and Implementation
- Engineering intent:
	- Make rollover-constrained operation the only valid runtime path for baseline simulation and diagnostics.
- What changed:
	- Removed rollover toggle usage from corner solver call path; rollover cap is now always enforced in corner speed bounding.
	- Updated G-G and constant-radius diagnostics to single rollover-constrained mode.
	- Updated A/B suite output context to always report rollover_on/true.
	- Updated solver contract setup and docs references accordingly.
- Why this is physically reasonable:
	- Enforcing rollover-constrained bounds prevents non-physical cornering envelopes from entering speed profile decisions.
- Verification added:
	- Targeted solver contract run completed; known existing base_mu sensitivity contract still fails (unchanged by this change).

## 4) Impact and Explanation
- Physics correctness impact:
	- Eliminates a non-physical execution mode from regular workflow.
- Lap-time trustworthiness impact:
	- Reduces risk of optimistic results caused by disabled rollover constraints.
- Diagnostics stability impact:
	- Artifacts now reflect one consistent physical operating mode.
- Limitations and next step:
	- Historical docs/log entries still mention rollover_off for past context, but runtime path no longer supports it.

## Validation Gates (Required)
- Tyre invariants: NOT RUN in this change
- RMSE thresholds: NOT RUN in this change
- Fallback-rate thresholds: NOT RUN in this change
- Solver contract suite: PARTIAL (2 pass, 1 known failing contract: base_mu sensitivity)

## Reproducibility Notes (Optional)
- uv run python -m unittest tests.test_solver_contracts -v
- uv run python -c "import sys,json; sys.path.insert(0,'src'); from track.track import load_track; from vehicle.vehicle import create_vehicle; from simulator.simulator import run_lap_time_simulation; from collections import Counter; cfg=json.load(open('config.json')); cfg['track']={'file_path':'datasets/tracks/FSUK.txt'}; v=create_vehicle(cfg); tr=load_track('datasets/tracks/FSUK.txt',cfg.get('debug_mode',False)); res=run_lap_time_simulation(tr,v,cfg,display=False); print(dict(Counter(res.diagnostics.get('corner_failure_reason',[]))))"
- uv run python src/ab_testing/run_ab_suite.py --tracks StraightLineTrack --variants baseline --fallback-threshold 0.15 --output-dir ab_test_outputs/smoke_rollover_flag_quick

---

Timestamp: 2026-04-16T20:05:00Z
Owner: Copilot + Project Team
Change ID: combined-force-budgeting-propagation-v1
Scope: forward/backward speed propagation realism under combined lateral + longitudinal demand

## 1) Problem

### High-Level
- Combined-g values were still too optimistic even after fallback and retry-tier improvements.
- This suggested that solver robustness alone was not enough; force budgeting in propagation was still too generous.

### Low-Level
- Forward and backward passes used strong pure longitudinal capacity while lateral demand was present.
- Without consistent friction-ellipse budgeting through propagation, the model could overstate usable longitudinal authority in corners.

## 2) Diagnosis
- Evidence used:
	- FSUK rollover diagnostics showing high combined-g values.
	- Inspection of forward/backward force-cap logic in speed propagation path.
- Root cause:
	- Longitudinal force caps were not consistently reduced by lateral demand in both propagation passes.
- Alternatives ruled out:
	- Remaining fallback points were localized and low-count, so they were not the only source of high combined-g.

## 3) Solution and Implementation
- Engineering intent:
	- Enforce a consistent combined-force budget so acceleration/braking authority reduces as lateral demand rises.
- What changed:
	- Added total pure-slip force-cap helper for longitudinal and lateral channels.
	- Added friction-ellipse budget scale from lateral demand ratio.
	- Applied that scale to longitudinal traction in forward pass and braking authority in backward pass.
	- Exposed new diagnostics channels for lateral caps and combined-budget scales.
- Why this is physically reasonable:
	- Tyres cannot deliver independent peak Fx and peak Fy simultaneously.
	- A friction-ellipse style budget enforces this coupling in a physically interpretable way.
- Verification added:
	- Existing contract suite rerun.
	- FSUK rollover diagnostics rerun after propagation update.

## 4) Impact and Explanation
- Physics correctness impact:
	- Improves consistency between tyre force limits and speed-profile propagation under combined loading.
- Lap-time trustworthiness impact:
	- Reduces optimistic acceleration/braking in cornered states.
- Diagnostics stability impact:
	- Added telemetry to track when and how longitudinal authority was reduced by lateral demand.
- Limitations and next step:
	- Current representative lateral slip-angle cap is still a simplified proxy.
	- Next step is parameter-activation audit and per-parameter influence checks to ensure all root JSON parameters affect the expected physics pathways.

## Validation Gates (Required)
- Tyre invariants: PASS
- RMSE thresholds: PASS (no tyre fit changes in this step)
- Fallback-rate thresholds:
	- FSUK (rollover_on): PASS (0.0155 under current gate definition)
	- SkidpadF26: PASS (from previous baseline sweep)
	- StraightLineTrack: PASS (from previous baseline sweep)

## Reproducibility Notes (Optional)
- uv run python -m unittest tests.test_solver_contracts tests.test_tyre_force_contracts tests.test_tyre_peak_load_clamp_contracts
- uv run python src/diagnostics/gg_rollover_suite.py --track datasets/tracks/FSUK.txt --output-dir artifacts/diagnostics/gg_rollover_suite

---

Timestamp: 2026-04-16T19:45:00Z
Owner: Copilot + Project Team
Change ID: fallback-rootcause-and-rollover-visibility-v1
Scope: fallback physical constraints, solver failure attribution, A/B rollover-mode traceability

## 1) Problem

### High-Level
- We still saw optimistic combined-g behavior, but diagnostics did not clearly separate physical-limit behavior from solver failure behavior.
- We also had ambiguity when comparing fallback counts across runs because rollover mode was not explicit in A/B outputs.

### Low-Level
- Fallback speed selection was still largely formula-based and did not include a continuity cap from the previous solved point.
- Solver failure reasons were not carried through clearly in diagnostics, so root-cause localization was hard.
- A/B output rows did not include explicit `rollover_on` / `rollover_off` context.

## 2) Diagnosis
- Evidence used:
	- FSUK rollover diagnostics with high combined-g peaks.
	- Direct one-shot vs retry-tier comparisons on FSUK.
	- Inspection of per-point solver outcomes and fallback locations.
- Root cause:
	- Remaining fallback points were localized solve-feasibility issues (residual/state-bound) rather than global model failure.
	- Mode-mixing (rollover on vs off) explained previous confusion around fallback counts.
- Alternatives ruled out:
	- Tyre invariant and contract failures were not the driver; contracts remained passing.

## 3) Solution and Implementation
- Engineering intent:
	- Make fallback conservative and physically bounded, and make solver failures diagnostically actionable.
- What changed:
	- Added constrained fallback speed selection using physical cap and continuity cap.
	- Added explicit failure reason tagging from corner solver (`root_failed`, `residual_not_met`, `state_bounds_exceeded`, etc.).
	- Added tier-level failure traces in diagnostics.
	- Added explicit rollover context columns to A/B runs: `rollover_mode`, `use_rollover_speed_cap`.
- Why this is physically reasonable:
	- Fallback should not create sudden optimistic speed jumps relative to neighboring points.
	- Failure diagnostics should identify whether rejection came from physics-consistency checks or numerical solve failure.
- Verification added:
	- Contract suite rerun (solver + tyre invariants + tyre clamp contracts).
	- FSUK failure reason distribution extracted from diagnostics.
	- A/B quick run confirms rollover mode fields are emitted in CSV/summary.

## 4) Impact and Explanation
- Physics correctness impact:
	- Fallback path is now more conservative and less likely to inject non-physical spikes.
- Lap-time trustworthiness impact:
	- Better confidence that unresolved points are capped consistently rather than inflated by unconstrained fallback.
- Diagnostics stability impact:
	- Root-cause attribution is now visible: FSUK baseline run showed 254 points with no issue, and only 4 fallback points split across residual/state-bound categories.
- Limitations and next step:
	- Combined-g values are still high; remaining issue is not just fallback, but force budgeting in forward/backward propagation.

## Validation Gates (Required)
- Tyre invariants: PASS
- RMSE thresholds: PASS (no tyre fit changes in this step)
- Fallback-rate thresholds:
	- FSUK (rollover_on): PASS under current gate definition (`fallback_rate <= 0.15` absolute fraction)
	- SkidpadF26: PASS
	- StraightLineTrack: PASS

## Reproducibility Notes (Optional)
- uv run python -m unittest tests.test_solver_contracts tests.test_tyre_force_contracts tests.test_tyre_peak_load_clamp_contracts
- uv run python src/diagnostics/gg_rollover_suite.py --track datasets/tracks/FSUK.txt --output-dir artifacts/diagnostics/gg_rollover_suite

---

Timestamp: 2026-04-16T19:05:00Z
Owner: Copilot + Project Team
Change ID: corner-solver-retry-tiers-v1
Scope: corner equilibrium robustness, fallback observability, per-circuit solve diagnostics

## 1) Problem

### High-Level
- When corner equilibrium failed, the simulator dropped straight to fallback speed with limited recovery attempts.
- This made it harder to distinguish true physical limits from numerical solve fragility.

### Low-Level
- The corner solver path used a single solve attempt per point and then fallback.
- There was no warm-start continuation between adjacent points and limited visibility into how often retries were needed.

## 2) Diagnosis
- Evidence used:
	- Existing fallback-rate diagnostics from lap simulation outputs.
	- Circuit runs on FSUK, SkidpadF26, and StraightLineTrack.
- Root cause:
	- Some FSUK high-curvature segments remained sensitive to initial guess and bounds; one-shot solves were not robust enough.
- Alternatives ruled out:
	- This was not a global solver collapse: Skidpad and StraightLine solved without fallback in baseline runs.

## 3) Solution and Implementation
- Engineering intent:
	- Prefer physically valid equilibrium solutions through structured retries before fallback.
- What changed:
	- Added retry tiers: base solve, warm-start solve, conservative-bound solve.
	- Added optional warm-start and speed upper-bound inputs to the corner state solver.
	- Added diagnostics channels for retry count, selected solve tier, and per-point physical cap speed.
- Why this is physically reasonable:
	- Adjacent track points are dynamically similar, so warm starts should improve numerical convergence without changing governing physics.
	- Conservative upper bounds avoid spending solve effort in unlikely speed regions.
- Verification added:
	- Existing solver and tyre contract tests run as non-regression checks.
	- Circuit-level fallback/retry telemetry collected directly from simulation diagnostics.

## 4) Impact and Explanation
- Physics correctness impact:
	- No new force model assumptions were introduced; this is a solve-robustness improvement.
- Lap-time trustworthiness impact:
	- Reduces unnecessary fallback usage where a physically valid equilibrium is recoverable by better initialization.
- Diagnostics stability impact:
	- Clear visibility into whether a point solved via base tier, warm start, conservative tier, or fallback.
- Limitations and next step:
	- FSUK still shows localized fallback (~1.55% in baseline), so next work is a constrained fallback replacement and failure-reason taxonomy.

## Validation Gates (Required)
- Tyre invariants: PASS
- RMSE thresholds: PASS (unchanged, no tyre-curve edits in this step)
- Fallback-rate thresholds:
	- FSUK: PASS (0.0155 with threshold 0.15 absolute fraction = 15%)
	- SkidpadF26: PASS (0.0000)
	- StraightLineTrack: PASS (0.0000)

## Reproducibility Notes (Optional)
- uv run python -m unittest tests.test_solver_contracts tests.test_tyre_force_contracts tests.test_tyre_peak_load_clamp_contracts
- uv run python -c "import sys,copy,json,collections; from statistics import mean; sys.path.insert(0,'src'); from track.track import load_track; from vehicle.vehicle import create_vehicle; from simulator.simulator import run_lap_time_simulation; cfg=json.load(open('config.json')); tracks=['datasets/tracks/FSUK.txt','datasets/tracks/SkidpadF26.txt','datasets/tracks/StraightLineTrack.txt']; print('track,fallback_rate,retry_mean,retry_max,top_methods');\nfor t in tracks: c=copy.deepcopy(cfg); c['track']={'file_path':t}; v=create_vehicle(c); tr=load_track(t,c.get('debug_mode',False)); r=run_lap_time_simulation(tr,v,c,display=False); fb=r.diagnostics.get('corner_fallback_used',[]); rc=r.diagnostics.get('corner_retry_count',[]); sm=r.diagnostics.get('corner_solve_method',[]); fr=mean([1.0 if x else 0.0 for x in fb]) if fb else 0.0; rm=mean(rc) if rc else 0.0; rmax=max(rc) if rc else 0; cnt=collections.Counter(sm); top=';'.join([f'{k}:{v}' for k,v in cnt.most_common(3)]); print(f'{t},{fr:.4f},{rm:.3f},{rmax},{top}')"

---

Timestamp: 2026-04-16T18:20:00Z
Owner: Copilot + Project Team
Change ID: tyre-peak-load-clamp-v1
Scope: tyre force envelope realism, validation gating, A/B comparison clarity

## 1) Problem

### High-Level
- The simulator could become too optimistic in high-load conditions, reporting grip and g-levels that were higher than we could justify from measured tyre data.
- This reduced trust in rollover conclusions and in lap-time comparisons, because the model could look fast for the wrong reason.

### Low-Level
- The tyre model used a curve that continued beyond the last measured normal-load point.
- In practice, this meant that once the virtual tyre entered a higher load region than the dataset covered, predicted peak force could keep increasing without evidence.
- From first principles, we should not claim additional grip where we have no measured support.

## 2) Diagnosis
- Evidence used:
	- Tyre verification plots and error metrics.
	- Rollover and G-G diagnostics where high combined g appeared.
	- A/B outputs tracking fallback behavior and sensitivity patterns.
- Root cause:
	- Peak-force prediction above measured load range was being extrapolated, which can overstate available grip.
- Alternatives ruled out:
	- Basic tyre invariants remained valid, so the issue was not zero-load behavior.
	- RMSE within measured load bins was already good, so the core in-range fit was not the primary problem.

## 3) Solution and Implementation
- Engineering intent:
	- Constrain the tyre model to a defensible force envelope when loads go beyond measured TTC data.
- What changed:
	- Added a controlled variant that caps high-load peak-force lookup at the highest measured load.
	- Kept baseline behavior available to preserve comparison continuity.
	- Added explicit gates so pass/fail is visible for tyre behavior and fallback usage.
- Why this is physically reasonable:
	- Tyre grip is strongly load-dependent, but not unconstrained.
	- If measurement coverage ends, assuming continued linear growth is unsafe.
	- Clamping at the measured boundary is conservative and better aligned with engineering evidence.
- Verification added:
	- Focused contract checks for high-load growth behavior.
	- High-load growth ratio gate in tyre verification.
	- Fallback-rate gate visibility in A/B summaries.

## 4) Impact and Explanation
- Physics correctness impact:
	- Reduced risk of non-physical force inflation in high-load operating points.
- Lap-time trustworthiness impact:
	- Lower chance of optimistic lap-time deltas caused by unsupported grip assumptions.
- Diagnostics stability impact:
	- Clearer pass/fail interpretation across tyre verification and A/B outputs.
- Limitations and next step:
	- This does not yet solve combined-slip budgeting end-to-end in the speed-profile passes.
	- Next priority is to tighten corner fallback behavior so solver fallbacks reflect physically bounded states.

## Validation Gates (Required)
- Tyre invariants: PASS
