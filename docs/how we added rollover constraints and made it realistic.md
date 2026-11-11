# Lessons Learned: Bringing G-Levels Back to Reasonable

## Audience
This note is for developers extending the current lap time simulator.

## Goal
Explain how the simulator moved from optimistic/unreasonable G behavior to a more reasonable baseline, and what principles must be preserved.

## Starting Problem
The simulator was producing optimistic grip and combined G behavior in some scenarios. This reduced trust in lap-time conclusions and made debugging harder.

## What Changed and Why It Worked

### 1) Tyre envelope was bounded to measured evidence
- Change: Added high-load peak-force clamping option in the tyre model path.
- Why it matters: If normal load goes beyond measured TTC data, unconstrained extrapolation can invent grip.
- Lesson: Never allow force models to claim additional capability outside validated data without an explicit, justified assumption.

### 2) Corner solve path became robust before fallback
- Change: Added retry tiers (base, warm-start, conservative bound).
- Why it matters: One-shot solver failure can look like physics failure when it is actually a numerical initialization problem.
- Lesson: Use continuation and bounded retries first; fallback should be a last resort.

### 3) Fallback became physically constrained
- Change: Fallback speed is now capped by physical limits and continuity from the previous point.
- Why it matters: Unconstrained fallback can inject unrealistic spikes into speed and G channels.
- Lesson: Fallback is a safety mechanism, not a performance estimate.

### 4) Combined-force budgeting was enforced in propagation
- Change: Forward/backward propagation now reduces longitudinal authority when lateral demand is high (friction-ellipse style budget).
- Why it matters: Tyres cannot deliver peak longitudinal and peak lateral simultaneously.
- Lesson: Keep force coupling consistent across all stages (corner solve, forward pass, backward pass, diagnostics).

### 5) Diagnostics were made interpretable
- Change: Added explicit rollover-mode visibility and solver failure-reason telemetry.
- Why it matters: Mixed-mode comparisons (rollover on/off) and opaque failures lead to false regression conclusions.
- Lesson: Make operating mode and failure reason explicit in artifacts.

## Fundamental Principle
The turning point was moving from optimistic independent limits to bounded, coupled constraints:
- measured tyre envelope
- robust equilibrium solve path
- constrained fallback
- combined-slip force budgeting

This combination is what made G behavior reasonable enough for current use.

## Current Practical Acceptance (Temporary)
- Peak lateral G around 1.3 g with rollover constraint enabled is considered reasonable for now.
- Treat values above 2.0 g peak lateral as a caution flag until further validation is done.

## Developer Checklist for Future Changes
Before merging changes that affect vehicle dynamics:
1. Confirm tyre invariants still pass.
2. Confirm tyre RMSE gates still pass.
3. Confirm diagnostics are running in rollover-constrained mode (`rollover_on`, `use_rollover_speed_cap=true`).
4. Check fallback rate and failure reasons, not just lap time.
5. Inspect G-G-V envelope for physically plausible shape and peaks.
6. Log the change in `docs/MAJOR_CHANGE_LOG.md` using the standard format.

## Anti-Patterns to Avoid
- Treating fallback speed as real physical capability.
- Letting extrapolated tyre force dominate high-load states.
- Comparing diagnostics across runs without confirming rollover mode.
- Tuning for lap-time reduction without checking G-envelope plausibility.

## Summary for New Developers
The simulator became reasonable not through one parameter tweak, but by enforcing physically defensible constraints at every stage of the pipeline. If one stage is left optimistic, unrealistic G behavior returns.