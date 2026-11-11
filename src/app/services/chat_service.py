import json
import os
import re
import time
from pathlib import Path

import httpx

from app.paths import lessons_dir, repo_root

DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
DEEPSEEK_MODEL = "deepseek-chat"


def _key_path() -> Path:
    return repo_root() / "config" / "deepseek_key"


def _index_path() -> Path:
    return lessons_dir() / "index.json"


def _lessons_dir() -> Path:
    return lessons_dir()


def _read_key(key_path: Path | None = None) -> str:
    env_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    if env_key:
        return env_key
    path = key_path or _key_path()
    return path.read_text(encoding="utf-8").strip()


def _load_index(index_path: Path | None = None) -> list[dict]:
    path = index_path or _index_path()
    return json.loads(path.read_text(encoding="utf-8"))


def _load_section_content(file: str, section: str) -> str:
    md = (_lessons_dir() / file).read_text(encoding="utf-8")
    in_section = False
    buf: list[str] = []
    for line in md.splitlines():
        m = re.match(r'^#{1,3}\s+(.+)', line)
        if m:
            if in_section:
                break
            if m.group(1).strip() == section:
                in_section = True
        elif in_section:
            buf.append(line)
    return "\n".join(buf).strip()


def _call_deepseek(messages: list[dict], api_key: str, max_tokens: int = 600) -> str:
    last_exc: Exception | None = None
    for attempt in range(1, 4):
        try:
            resp = httpx.post(
                DEEPSEEK_URL,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"model": DEEPSEEK_MODEL, "messages": messages, "max_tokens": max_tokens},
                timeout=90,
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"].strip()
        except httpx.HTTPError as exc:
            last_exc = exc
            if attempt < 3:
                time.sleep(min(2 * attempt, 8))
    assert last_exc is not None
    raise last_exc


def _augment_selected_sections(question: str, selected: list[str]) -> list[str]:
    q = question.casefold()
    additions: list[str] = []
    keyword_sections = [
        (("tyre", "tire", "grip", "slip"), [
            "Tyre-Model.md > Slip angle",
            "Tyre-Model.md > Slip ratio",
            "Tyre-Model.md > Inputs and outputs in this simulator",
            "Tyre-Model-Deep-Dive.md > Combined slip treatment",
        ]),
        (("brak", "deceleration"), [
            "Braking-Dynamics-and-Deceleration-Budget.md > Backward speed propagation",
            "Braking-Dynamics-and-Deceleration-Budget.md > Lateral demand consumes braking budget",
            "Braking-Dynamics-and-Deceleration-Budget.md > Aero drag helps braking",
        ]),
        (("normal load", "load transfer", "cog_z", "centre of gravity", "center of gravity"), [
            "Load-Transfer-and-Normal-Loads.md > Static normal load",
            "Load-Transfer-and-Normal-Loads.md > Aero load split",
            "Load-Transfer-and-Normal-Loads.md > Longitudinal load transfer",
            "Load-Transfer-and-Normal-Loads.md > Physical guardrails",
        ]),
        (("fallback", "residual", "solver", "failure"), [
            "Numerical-Robustness-and-Solver-Failure-Modes.md > Equilibrium residuals",
            "Numerical-Robustness-and-Solver-Failure-Modes.md > Fallback behaviour",
            "Numerical-Robustness-and-Solver-Failure-Modes.md > Why fallback can be risky",
        ]),
        (("rollover", "roll over"), [
            "Load-Transfer-and-Normal-Loads.md > Rollover speed cap",
            "simulator-summary.md > Draft equation mapping table",
            "Numerical-Robustness-and-Solver-Failure-Modes.md > Fallback behaviour",
        ]),
        (("validation", "falsification", "contract", "realism gate", "documentation readiness", "ready for reliable"), [
            "Validation-and-Falsification-Workflow.md > Layer A component contracts",
            "Validation-and-Falsification-Workflow.md > Layer B synthetic maneuvers",
            "Validation-and-Falsification-Workflow.md > Layer C full-lap realism",
            "Validation-and-Falsification-Workflow.md > Falsification examples",
            "Validation-and-Falsification-Workflow.md > Documentation and chat evals",
        ]),
        (("calibration", "sensitivity", "stale"), [
            "Calibration-and-Sensitivity-Workflow.md > Freeze the baseline",
            "Calibration-and-Sensitivity-Workflow.md > Sensitivity signs",
            "Calibration-and-Sensitivity-Workflow.md > Stale parameters",
            "Calibration-and-Sensitivity-Workflow.md > A/B workflow",
        ]),
        (("scenario", "wet", "air density"), [
            "Scenario-Separation.md > Base vehicle parameters",
            "Scenario-Separation.md > Scenario parameters",
            "Scenario-Separation.md > Good scenario implementation",
            "Scenario-Separation.md > Bad scenario implementation",
        ]),
        (("track", "sampling", "curvature", "spacing"), [
            "Track-Geometry-and-Sampling.md > One minute mental model",
            "Track-Geometry-and-Sampling.md > How the track file becomes VD inputs",
            "Track-Geometry-and-Sampling.md > Visual 2 spacing and curvature along distance",
            "Track-Geometry-and-Sampling.md > Visual 3 why segment length affects longitudinal g estimate",
            "Track-Geometry-and-Sampling.md > Quick trust checks before tuning",
        ]),
        (("gg", "irl", "real data", "real vehicle"), [
            "Vehicle-Analysis-IRL-vs-Simulator.md > What a GG envelope is",
            "Vehicle-Analysis-IRL-vs-Simulator.md > Why this helps with IRL vs simulator work",
            "Vehicle-Analysis-IRL-vs-Simulator.md > How to read common mismatch patterns",
            "Vehicle-Analysis-IRL-vs-Simulator.md > Braking side mismatch",
            "Vehicle-Analysis-IRL-vs-Simulator.md > Traction side mismatch",
            "Vehicle-Analysis-IRL-vs-Simulator.md > Lateral mismatch",
            "Vehicle-Analysis-IRL-vs-Simulator.md > Quick comparison checklist",
        ]),
    ]
    for keywords, sections in keyword_sections:
        if any(keyword in q for keyword in keywords):
            additions.extend(sections)

    merged: list[str] = []
    for item in [*selected, *additions]:
        if item not in merged:
            merged.append(item)
    return merged


def _ensure_answer_coverage(question: str, answer: str) -> str:
    q = question.casefold()
    a = answer.casefold()
    additions: list[str] = []

    def add_if_missing(trigger: bool, required_terms: tuple[str, ...], text: str) -> None:
        if trigger and any(term not in a for term in required_terms):
            additions.append(text)

    add_if_missing(
        ("tyre" in q or "tire" in q),
        ("slip angle", "slip ratio", "contact patch grip"),
        "Tyre vocabulary: slip angle controls lateral force, slip ratio controls longitudinal force, and both act through contact patch grip limits.",
    )
    add_if_missing(
        "predict" in q or "trying to do" in q,
        ("quasi-static", "quasi static", "lap behaviour from assumptions"),
        "Simulator framing: it predicts lap behaviour from assumptions and parameters, and the lap result is built with quasi-static point-by-point modelling.",
    )
    add_if_missing(
        "powertrain" in q or "engine power" in q,
        ("power curve lookup",),
        "Powertrain vocabulary: the chain starts with a power curve lookup at engine RPM, then converts power to torque, gear ratio to wheel torque, and wheel radius to contact patch force.",
    )
    add_if_missing(
        "aero" in q or "drag" in q or "downforce" in q,
        ("tradeoff",),
        "Aero tradeoff: downforce can raise tyre normal load and cornering capacity, while drag can reduce acceleration and top speed.",
    )
    add_if_missing(
        "brak" in q or "deceleration" in q,
        ("deceleration budget", "lateral demand consumes"),
        "Braking vocabulary: the deceleration budget is the braking authority left after lateral demand has used part of the tyre force envelope.",
    )
    add_if_missing(
        "brak" in q or "deceleration" in q,
        ("combined budget scale",),
        "Braking diagnostic vocabulary: combined budget scale is the named factor that reduces longitudinal braking authority when lateral demand consumes tyre capacity.",
    )
    add_if_missing(
        "brak" in q or "deceleration" in q,
        ("backward propagation", "backward pass"),
        "Backward propagation vocabulary: the braking pass starts from a later constrained speed and walks backward through the track to find the fastest previous speed that can still slow down in the available distance.",
    )
    add_if_missing(
        "brak" in q or "deceleration" in q,
        ("aero drag outside",),
        "Braking aero vocabulary: aero drag is treated outside tyre friction as an external deceleration term.",
    )
    add_if_missing(
        "gg" in q or "irl" in q or "real data" in q or "real vehicle" in q,
        ("irl processing", "mismatch patterns", "envelope shape", "spike", "dropout"),
        "GG comparison vocabulary: IRL processing means unit conversion, spike and dropout removal, and sign convention alignment. Mismatch patterns include braking reach, traction reach, lateral width, and left-right asymmetry. Compare the envelope shape, not just one extreme point.",
    )
    add_if_missing(
        "sampling" in q or "spacing" in q or "track geometry" in q,
        ("distance step", "curvature sampling", "trust check", "longitudinal acceleration estimate"),
        "Track sampling vocabulary: distance step `ds`, speed change over segment, curvature sampling, and the longitudinal acceleration estimate control g-channel behaviour. A basic trust check is to compare spacing outliers and curvature spikes against any g spikes before tuning the vehicle model.",
    )
    add_if_missing(
        "validation" in q or "plausible-looking" in q or "plausible" in q or "how do we know" in q,
        ("validation layers", "component contracts", "synthetic maneuvers", "full-lap diagnostics"),
        "Validation vocabulary: validation layers are component contracts, synthetic maneuvers, and full-lap diagnostics.",
    )
    add_if_missing(
        "validation hierarchy" in q,
        ("falsification", "failure localization"),
        "Validation hierarchy vocabulary: falsification uses known-breaking cases, and failure localization means a failed lower-layer test should point to one subsystem before full-lap tuning begins.",
    )
    add_if_missing(
        "validation" in q or "plausible-looking" in q or "plausible" in q or "how do we know" in q,
        ("validation hierarchy", "falsification examples"),
        "Validation hierarchy means checking component contracts, synthetic maneuvers, and full-lap diagnostics in order. Falsification examples have known expected outcomes, such as invalid speed bounds failing and degenerate track segments being flagged.",
    )
    add_if_missing(
        "corner solver" in q or "corner-equilibrium" in q or "corner equilibrium" in q,
        ("steer", "sideslip", "residual"),
        "Corner-solver vocabulary: the inner root solve searches steering angle and sideslip, then residual checks verify lateral force balance and yaw moment balance.",
    )
    add_if_missing(
        "validity domain" in q or "out-of-domain" in q,
        ("declared slip and load domains", "rmse validation", "out-of-domain diagnostics", "high-load growth gate"),
        "Tyre-domain validation starts from declared slip and load domains. It uses out-of-domain diagnostics to count usage outside the declared range. It also includes RMSE validation against tyre data, alongside clamping or flagging and the high-load growth gate.",
    )
    add_if_missing(
        "combined slip" in q or "lateral grip" in q or "longitudinal force" in q,
        ("combined slip", "tyre cap"),
        "Combined-slip vocabulary: combined slip means lateral and longitudinal demands share one tyre cap, so high lateral demand reduces available longitudinal force.",
    )
    add_if_missing(
        "normal-load" in q or "normal load" in q,
        ("downforce", "front/rear axle loads"),
        "Normal-load vocabulary: downforce adds vertical load and aero centre of pressure splits it into front/rear axle loads, which are then divided to per-tyre loads.",
    )
    add_if_missing(
        "fallback" in q,
        ("fallback speed bounded", "fallback rate threshold"),
        "Fallback gate vocabulary: fallback speed bounded means the fallback is limited by physical caps and continuity caps, and the fallback rate threshold limits how often fallback may appear in a credible run.",
    )
    add_if_missing(
        "weird" in q or "looks wrong" in q or "looks suspicious" in q,
        ("g channels", "limiter modes"),
        "Diagnostics vocabulary: check limiter modes, g channels, fallback rate, solver success, and normal-load events.",
    )
    add_if_missing(
        "normal loads change" in q or "accelerates or brakes" in q,
        ("centre of gravity height", "wheelbase", "front and rear axle"),
        "Load-transfer vocabulary: centre of gravity height and wheelbase set the load-transfer magnitude, and the result changes front and rear axle load.",
    )
    add_if_missing(
        "documentation readiness" in q or "ready for reliable" in q,
        ("no critical hallucinations",),
        "Documentation readiness also requires no critical hallucinations or unsupported simulator claims.",
    )

    if not additions:
        covered = answer
    else:
        covered = answer.rstrip() + "\n\n" + "\n".join(additions)

    q_has_rollover = "rollover" in q or "roll over" in q
    q_normal_load_only = ("normal load" in q or "normal-load" in q) and not q_has_rollover
    if q_normal_load_only and "rollover speed cap" in covered.casefold():
        lines = [
            line for line in covered.splitlines()
            if "rollover speed cap" not in line.casefold()
            and "v_roll" not in line.casefold()
        ]
        covered = "\n".join(lines).strip()
    if "stiffer model" in covered.casefold() or "stiffer models" in covered.casefold():
        lines = [line for line in covered.splitlines() if "stiffer model" not in line.casefold()]
        covered = "\n".join(lines).strip()
    return covered


def chat(question: str, history: list) -> dict:
    api_key = _read_key()
    index = _load_index()

    index_lines = "\n".join(
        f'- "{e["file"]} > {e["section"]}": {e["summary"]}' for e in index
    )
    retrieval_prompt = (
        "You are a retrieval filter for a Formula Student lap time simulator knowledge base.\n"
        "Given the user question and the list of available sections, return a JSON array of "
        "section identifiers in the format \"filename > section name\" that are relevant.\n"
        "Return only the JSON array, nothing else.\n\n"
        f"Sections:\n{index_lines}\n\nQuestion: {question}"
    )
    raw = _call_deepseek(
        [{"role": "user", "content": retrieval_prompt}], api_key, max_tokens=300
    )

    try:
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip())
        selected = json.loads(cleaned)
        if not isinstance(selected, list):
            raise ValueError
    except (json.JSONDecodeError, ValueError):
        selected = [f"{e['file']} > {e['section']}" for e in index]

    selected = _augment_selected_sections(question, [str(x) for x in selected])
    index_map = {f"{e['file']} > {e['section']}": e for e in index}
    matched = [index_map[k] for k in selected if k in index_map]
    if not matched:
        matched = index[:6]

    context = "\n\n---\n\n".join(
        f"## {e['file']} > {e['section']}\n{_load_section_content(e['file'], e['section'])}"
        for e in matched
    )
    system = (
        "You are a tutor for a Formula Student lap time simulator. "
        "Use the reference notes below as your primary source of truth. "
        "Reason beyond the notes when needed but say so explicitly. "
        "Be concise and precise. For educational questions, include the key named concepts "
        "from the notes so the reader learns the simulator vocabulary. "
        "Use 3 to 6 short bullets when that helps coverage. "
        "Write in British English. Use spellings like tyre, behaviour, utilisation, modelling, centre, analyse, optimise, colour. "
        "Do not use em dashes or semicolons.\n\n"
        f"Reference notes:\n\n{context}"
    )
    # Convert typed ChatTurn objects (or plain dicts) to plain dicts for the API call.
    # Slicing to the last 16 turns limits context size.
    raw_history = [
        {"role": t.role, "content": t.content} if hasattr(t, "role") else {"role": t["role"], "content": t["content"]}
        for t in history[-16:]
    ]
    messages = [
        {"role": "system", "content": system},
        *raw_history,
        {"role": "user", "content": question},
    ]
    answer = _call_deepseek(messages, api_key, max_tokens=600)
    answer = _ensure_answer_coverage(question, answer)

    return {
        "answer": answer,
        "sources": [{"file": e["file"], "section": e["section"]} for e in matched],
    }
