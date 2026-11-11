# Claude Frontend Guide

## Mission
Build and evolve a local engineer app that runs the simulator core and presents clear inputs and outputs.
Keep trust high through first principles framing and code level traceability.

## Product Context
Users are engineers who need fast parameter testing and easy visual interpretation.
Every page should explain what the model does and why the result is credible for the real car.

## Design Direction
Theme is inspired by "The Wind Rises" (Studio Ghibli) — engineering document aesthetic, folder tabs as navigation, clean spec sheet structure.
Use clear hierarchy, compact controls, and practical data views.
Do not add animation unless explicitly requested.
No gradients anywhere in the UI.
No purple.
No stock or default icons — use text labels only.
Graph and chart colors use the charting library defaults. The color palette is reserved for website chrome only.

## Color Palette
Use the LGR car livery as the base.

- Green primary `#006B5C`
- Red accent `#C1122F`
- Carbon black `#101215`
- Silver `#A7AEB6`
- Off white `#F4F6F8`
- Light surface `#E8ECF0` (inactive tabs, card surfaces)

## Copywriting Rules
Apply these rules to all user facing text in the app.

- Never use em dash
- Never use semicolon
- Never use colon
- Keep one to two ideas per sentence
- Keep language concrete and direct
- Do not inflate claims

## Trust Model
Always include both views below.

- High level physics summary
- Low level implementation summary

Every analysis page should show

- Governing equations in simple form
- Assumptions and model limits
- Runtime path to code files
- Validation evidence when available

## Relevant Files
Core simulator

- `src/simulator/simulator.py`
- `src/simulator/util/calcSpeedProfile.py`
- `src/simulator/util/vehicleDynamics.py`
- `src/vehicle/vehicle.py`
- `src/track/track.py`

Local app scaffold

- `src/app/run_local_app.py`
- `src/app/web.py`
- `src/app/schemas.py`
- `src/app/services/lap_service.py`
- `src/app/services/lift_coast_service.py`
- `src/app/static/index.html`
- `src/app/static/app.js`
- `src/app/static/styles.css`

Launch and packaging

- `tools/app/launch_sim_bt.ps1`
- `tools/app/launch_workbench.sh`
- `tools/app/build_windows_exe.ps1`

Physics docs and scope

- `docs/PARAMETER_ENFORCEMENT_AUDIT_ROADMAP.md`
- `docs/parameters/README.md`
- `docs/parameters/Aero-CoP-Deep-Dive.md`
- `docs/parameters/Deferred-Parameters.md`
- `docs/MAJOR_CHANGE_LOG.md`

## Frontend Architecture Rules
Keep simulator logic in backend services.
Frontend should orchestrate inputs, calls, and visual outputs only.

Use one service module per capability.
Each capability should have

- Input schema
- Runner function
- Output schema
- Page section in UI

## Feature Expansion Path
Add features as service plus page pairs.
Examples

- Parameter sweep page
- Lap diagnostics page
- Lift and coast strategy page
- Validation and gates page

## Performance and Size Goals
Keep dependencies minimal.
Prefer static web assets and lightweight charting.
Avoid heavy frontend frameworks unless needed by scope.

## Definition of Done for New Pages
A new page is complete when all checks pass.

- Calls simulator backed service
- Shows clear inputs and outputs
- Includes high level and low level trust notes
- States assumptions and limits
- Preserves copywriting and visual rules
