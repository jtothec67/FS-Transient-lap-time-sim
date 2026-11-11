# Major Change Entry Template

Timestamp: YYYY-MM-DDTHH:MM:SSZ
Owner: <name>
Change ID: <short-id>
Scope: <system area affected>

Reading goal:
- This log is written for engineers first, not just code contributors.
- Explain the physical reasoning and trade-offs before implementation details.

## 1) Problem

### High-Level
- <What was going wrong in the simulator behavior, and why did it matter?>

### Low-Level
- <What specific model assumption or mechanism caused the issue?>
- <What symptom did this create in outputs (for example unrealistic g-levels, unstable lap times, stale sensitivity)?>

## 2) Diagnosis
- Evidence used:
	- <Which diagnostics, plots, or checks were used?>
- Root cause:
	- <What was confirmed and why?>
- Alternatives ruled out:
	- <What looked plausible but was proven not to be the primary cause?>

## 3) Solution and Implementation
- Engineering intent:
	- <What principle did we enforce? (for example: do not exceed measured tyre envelope)>
- What changed:
	- <Plain-language summary of the change>
- Why this is physically reasonable:
	- <Short explanation from first principles>
- Verification added:
	- <What gates/tests were added or updated?>
- Implementation notes (optional):
	- <Short technical notes if needed>

## 4) Impact and Explanation
- Physics correctness impact:
	- <How realism improved>
- Lap-time trustworthiness impact:
	- <How confidence in predicted pace changed>
- Diagnostics stability impact:
	- <How outputs became easier to trust and compare>
- Limitations and next step:
	- <What remains incomplete and what should be tackled next>

## Validation Gates (Required)
- Tyre invariants: PASS/FAIL
- RMSE thresholds: PASS/FAIL
- Fallback-rate thresholds: PASS/FAIL

## Reproducibility Notes (Optional)
- <Key command(s) used, only if helpful for repeatability>
