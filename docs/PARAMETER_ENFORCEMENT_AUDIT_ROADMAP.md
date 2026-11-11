# Parameter Enforcement Audit Roadmap

Purpose: verify that every parameter in `parameters.json` is physically enforced, has the expected directional effect, and does not create hidden coupling in unrelated subsystems.

Why this exists:
- Milestones 1-6 established a first-principles core and hard-gate workflow.
- The next reliability layer is parameter-level enforcement: every parameter must be traceable to governing equations and validated by contracts.

## Operating Context and Baseline Assumptions

This roadmap is explicitly scoped to the current Formula Student vehicle model.

Non-negotiable assumptions for this audit:
- The current `parameters.json` values are treated as the approved baseline.
- Powertrain context is a Honda motorbike engine and gearbox integrated into the Formula Student car model.
- Current final-drive and gearing values, even if unusual versus textbook references, are treated as valid design baseline for enforcement checks.

Implication for audit decisions:
- The audit verifies physical enforcement and directional correctness of parameters.
- The audit does not "normalize" parameters to generic automotive expectations unless there is explicit evidence of physics inconsistency or a user-requested redesign.

---

## Audit Goals

1. Parameter completeness:
- Every parameter in `parameters.json` is either:
  - physically enforced in runtime calculations, or
  - explicitly marked as metadata/deferred.

2. Parameter correctness:
- Directional behavior is physically consistent (sign and monotonicity checks).
- Magnitude sensitivity is non-trivial where expected.

3. Baseline fidelity:
- Parameter enforcement must preserve current baseline behavior for the Formula Student package unless a deliberate, logged design change is made.
- Drivetrain checks must validate the Honda engine/gearbox + current final-drive stack as implemented, not against external "typical" gearing assumptions.

4. Parameter isolation:
- Parameter changes should affect intended channels only.
- No hidden coupling into unrelated outputs.

5. Reproducibility:
- All checks are executable via deterministic commands.
- Major design changes are logged in `docs/MAJOR_CHANGE_LOG.md`.

---

## Execution Strategy

Use short, focused loops to avoid long-run churn:
- Phase A: static trace + low-cost contracts.
- Phase B: medium-cost synthetic checks.
- Phase C: full-track A/B strict gates.

Do not jump to full runs before Phase A and B pass.

---

## Parameter Inventory (Current)

Source file: `parameters.json`

General:
- `mass`
- `base_mu`

Aerodynamics:
- `frontal_area`
- `drag_coefficient`
- `downforce_coefficient`
- `aero_cp`

Geometry:
- `wheelbase`
- `front_track_width`
- `rear_track_width`
- `cog_z`
- `cog_longitudinal_pos`
- `max_cog_z`

Vehicle dynamics:
- `roll_stiffness`
- `suspension_stiffness`
- `damping_coefficient`
- `max_roll_angle_deg`

Drivetrain:
- `wheel_radius`
- `final_drive_ratio`
- `gear_ratios`
- `transmission_efficiency`

---

## Phase 1: Static Mapping and Gap Detection

Deliverable:
- Parameter trace matrix in this file (update in-place as rows are completed).

For each parameter, capture:
- Where loaded.
- Where used in equations.
- Expected sign/monotonic effect.
- Existing test coverage.
- Gap status.

### Trace Matrix Template

| Parameter | Load path | Runtime equation/path | Expected effect | Existing test/gate | Status |
|---|---|---|---|---|---|
| `mass` | `vehicle.load_vehicle_parameters` | Inertia terms and force-to-acceleration conversions in speed profile and corner solve | Higher value reduces accel/brake and lateral accel for fixed tyre force | Milestone contracts and runtime gates active | PARTIAL |
| `base_mu` | `vehicle.load_vehicle_parameters` | Tyre peak force scaling (`LookupTableTyreModel`) and fallback cap logic | Higher value raises available tyre force and lateral speed cap | Milestone 3 base-mu sensitivity gate and tyre contracts | OK |
| `frontal_area` | `vehicle.load_vehicle_parameters` | `Vehicle.compute_aero_drag`, `Vehicle.compute_downforce` | Higher value increases drag and downforce magnitude | `tests.test_parameter_enforcement_contracts` | OK |
| `drag_coefficient` | `vehicle.load_vehicle_parameters` | `Vehicle.compute_aero_drag` | Higher value increases drag, reduces acceleration/top speed | `tests.test_parameter_enforcement_contracts` | OK |
| `downforce_coefficient` | `vehicle.load_vehicle_parameters` | `Vehicle.compute_downforce`; threaded into longitudinal and corner normal-load states | Higher value increases downforce and induced drag | `tests.test_parameter_enforcement_contracts`; A/B sensitivity | OK |
| `aero_cp` | `vehicle.load_vehicle_parameters` (alias `aero_centre_of_pressure`) | `_split_aero_load_by_cp` in `calcSpeedProfile`; front/rear tyre loads passed into corner solve | Moves aero load balance front/rear while preserving total aero load | `tests.test_parameter_enforcement_contracts`; FSUK sensitivity probe | OK |
| `wheelbase` | `vehicle.load_vehicle_parameters` | Static load split and yaw/corner state geometry terms | Changes axle load split and corner state solution geometry | Indirect coverage in limiting-case suite | PARTIAL |
| `front_track_width` | `vehicle.load_vehicle_parameters` | Rollover speed cap and corner-state geometry | Wider track increases rollover threshold and lateral stability margin | Milestone A/B focused sensitivity channel | PARTIAL |
| `rear_track_width` | `vehicle.load_vehicle_parameters` | Effective CoG/roll helper and rollover-related checks | Wider rear track increases rollover threshold | Milestone A/B focused sensitivity channel | PARTIAL |
| `cog_z` | `vehicle.load_vehicle_parameters` | Longitudinal load transfer, rollover cap, roll checks | Higher CoG increases load transfer/roll and should hurt curved-track stability | Milestone 3 cog-z sign gate | OK |
| `cog_longitudinal_pos` | `vehicle.load_vehicle_parameters` | Static front/rear gravity load split in longitudinal and corner states | Shifts baseline front/rear normal loads and traction balance | No dedicated monotonic contract yet | PARTIAL |
| `max_cog_z` | `vehicle.load_vehicle_parameters` | `estimate_effective_cog_z` feasibility margin | Lower threshold should tighten feasibility envelope | No dedicated gate with strict threshold assertion | PARTIAL |
| `roll_stiffness` | `vehicle.load_vehicle_parameters` | Roll-angle computation and rollover margin checks | Higher stiffness reduces roll angle for fixed lateral load | Milestone A/B focused sensitivity channel | PARTIAL |
| `suspension_stiffness` | `vehicle.load_vehicle_parameters` | Deferred in current quasi-static solver architecture | Should affect heave/roll response in a transient-capable model | Deferred for production v1 scope | DEFERRED |
| `damping_coefficient` | `vehicle.load_vehicle_parameters` | Deferred in current quasi-static solver architecture | Should affect transient damping in a transient-capable model | Deferred for production v1 scope | DEFERRED |
| `max_roll_angle_deg` | `vehicle.load_vehicle_parameters` | `check_roll_constraint` and rollover feasibility checks | Lower threshold should reduce feasible lateral envelope | Milestone A/B focused sensitivity channel | PARTIAL |
| `wheel_radius` | `vehicle.load_vehicle_parameters` | RPM conversion and wheel-torque-to-force conversion | Larger radius lowers wheel force and changes RPM mapping | `tests.test_parameter_enforcement_contracts` | OK |
| `final_drive_ratio` | `vehicle.load_vehicle_parameters` | Wheel torque and RPM mapping (`compute_engine_rpm`, wheel torque path) | Higher ratio raises wheel torque and engine RPM at fixed speed | `tests.test_parameter_enforcement_contracts` | OK |
| `gear_ratios` | `vehicle.load_vehicle_parameters` | Gear selection and torque mapping | Ratio stack changes acceleration envelope and speed/RPM operating points | `tests.test_parameter_enforcement_contracts` | OK |
| `transmission_efficiency` | `vehicle.load_vehicle_parameters` | Wheel torque scaling in powertrain path | Lower efficiency reduces wheel torque and acceleration | `tests.test_parameter_enforcement_contracts` | OK |

Status values:
- `OK`: enforced and tested.
- `PARTIAL`: enforced but weak/no direct contract.
- `GAP`: loaded but not physically enforced.
- `DEFERRED`: intentionally not in scope, with documented reason.

---

## Phase 2: Aero-First Audit (Priority)

Start here because aero has highest risk of "loaded but not physically enforced" behavior.

### 2.1 Aerodynamic force path checks

Check and lock:
- `frontal_area` directional check.
- `drag_coefficient` directional check.
- `downforce_coefficient` directional check.
- `air_density` and scenario air-density scaling directional check.

Contracts to add:
- Increasing `drag_coefficient` at fixed speed increases drag force.
- Increasing `frontal_area` at fixed speed increases both drag and downforce.
- Increasing `downforce_coefficient` at fixed speed increases downforce.

### 2.2 Aero center of pressure (`aero_cp`) enforcement check

Required outcome:
- Either:
  - physically enforce `aero_cp` into front/rear normal load split (preferred), or
  - mark as deferred with explicit rationale and remove from active sensitivity sweep.

Contract if enforced:
- Front/rear load distribution shifts with `aero_cp` while total aero load remains consistent.

---

## Phase 3: Geometry and Load Transfer Audit

Parameters:
- `wheelbase`, `front_track_width`, `rear_track_width`, `cog_z`, `cog_longitudinal_pos`, `max_cog_z`.

Checks:
- Sign/monotonicity for load-transfer and rollover constraints.
- No non-physical normal load events.
- Corner-solve, forward, backward use consistent load channels.

Contracts:
- Higher `cog_z` should not improve curved-track lap realism metrics.
- Track width changes should directionally affect rollover/lateral limits.

---

## Phase 4: Drivetrain and Longitudinal Audit

Parameters:
- `wheel_radius`, `final_drive_ratio`, `gear_ratios`, `transmission_efficiency`.

Checks:
- RPM conversion consistency.
- Torque-to-force conversion directionality.
- Gear selection changes acceleration envelope in expected direction.
- Honda engine/gearbox + final-drive mapping remains internally consistent with current baseline parameters.

Contracts:
- Lower `transmission_efficiency` reduces wheel force.
- Gear ratio changes alter wheel torque and acceleration trajectory.
- Baseline final-drive ratio and gear stack remain accepted reference; tests verify enforcement correctness, not whether ratios look "normal".

---

## Phase 5: Vehicle Dynamics Parameter Audit

Parameters:
- `roll_stiffness`, `suspension_stiffness`, `damping_coefficient`, `max_roll_angle_deg`.

Checks:
- Parameters are either physically connected or explicitly deferred.
- If connected, directional checks are enforced by contracts.

Note:
- For production v1, transient-only parameters that are not representable in the current quasi-static architecture are marked `DEFERRED` with explicit rationale and removed from active tuning decisions.

---

## Phase 6: Gate Integration and CI Flow

Integrate parameter-audit checks into a single command flow:

1) Fast contracts:
```bash
uv run python -m unittest tests.test_falsification_and_scenario_contracts tests.test_limiting_case_contracts -v
```

2) Parameter enforcement contracts:
```bash
uv run python -m unittest tests.test_parameter_enforcement_contracts -v
```

3) Strict A/B gates:
```bash
uv run python src/ab_testing/run_ab_suite.py --tracks FSUK,SkidpadF26,StraightLineTrack --variants baseline --output-dir ab_test_outputs/parameter_audit_strict --fallback-threshold 0.15 --stale-threshold 0.05 --max-out-of-domain-count 130000 --enforce-milestone3-gates --enforce-milestone4-gates --enforce-milestone5-gates --enforce-milestone6-gates --scenario-name baseline --scenario-grip-scale 1.0 --scenario-air-density-scale 1.0 --m5-max-abs-glat-g 2.0 --m5-max-gtotal-g 4.45
```

---

## Definition of Done (Parameter Audit)

The audit is complete when all conditions hold:
- Every parameter in `parameters.json` has status `OK` or `DEFERRED` with rationale.
- No `GAP` rows remain in trace matrix.
- Parameter enforcement contracts pass.
- Strict A/B gates pass in baseline scenario.
- At least one non-baseline scenario run passes Milestone 6 gates.
- All major design changes are recorded in `docs/MAJOR_CHANGE_LOG.md`.

---

## Immediate Next Steps (Actionable)

1. Keep `suspension_stiffness` and `damping_coefficient` as `DEFERRED` for production v1 and exclude them from active setup/tuning recommendations.
2. Add direct monotonic contracts for geometry/load parameters currently `PARTIAL` (`wheelbase`, `cog_longitudinal_pos`, `max_cog_z`, track widths, roll stiffness).
3. Re-run strict gate command and log outcomes for baseline plus at least one non-baseline scenario.
4. Promote remaining `PARTIAL` rows to `OK` once dedicated contracts are merged and passing.