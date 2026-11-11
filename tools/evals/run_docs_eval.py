import argparse
import json
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DOCS_DIR = REPO_ROOT / "docs"
LESSONS_DIR = DOCS_DIR / "lessons"
QA_PATH = DOCS_DIR / "evals" / "simulator_qa.jsonl"
GOALS_PATH = DOCS_DIR / "DOCUMENTATION_GOALS.md"
LESSONS_README = LESSONS_DIR / "README.md"
LESSON_INDEX = LESSONS_DIR / "index.json"

REQUIRED_LESSONS = [
    "Simulator-Basics.md",
    "Tyre-Model.md",
    "Tyre-Model-Deep-Dive.md",
    "Powertrain-Model.md",
    "Aero-Model.md",
    "Load-Transfer-and-Normal-Loads.md",
    "Braking-Dynamics-and-Deceleration-Budget.md",
    "Vehicle-Modelling.md",
    "simulator-summary.md",
    "Numerical-Robustness-and-Solver-Failure-Modes.md",
    "Vehicle-Modelling-Diagnostics.md",
    "Vehicle-Analysis-IRL-vs-Simulator.md",
    "Track-Geometry-and-Sampling.md",
    "Validation-and-Falsification-Workflow.md",
    "Calibration-and-Sensitivity-Workflow.md",
    "Scenario-Separation.md",
]

STANDARD_SECTIONS = [
    "Read this after",
    "Goal",
    "Next lesson",
    "Related lessons",
]


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                row = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise SystemExit(f"{path}:{line_no}: invalid JSON: {exc}") from exc
            row["_line"] = line_no
            rows.append(row)
    return rows


def load_index() -> list[dict[str, Any]]:
    if not LESSON_INDEX.exists():
        return []
    return json.loads(LESSON_INDEX.read_text(encoding="utf-8"))


def indexed_markdown_headings(path: Path) -> list[str]:
    headings: list[str] = []
    heading: str | None = None
    buf: list[str] = []
    in_fence = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("```"):
            in_fence = not in_fence
        if in_fence:
            buf.append(line)
            continue
        match = re.match(r"^#{1,3}\s+(.+)", line)
        if match:
            if heading and "\n".join(buf).strip():
                headings.append(heading)
            heading = match.group(1).strip()
            buf = []
        else:
            buf.append(line)
    if heading and "\n".join(buf).strip():
        headings.append(heading)
    return headings


def all_markdown_headings(path: Path) -> list[str]:
    headings: list[str] = []
    in_fence = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        match = re.match(r"^#{1,3}\s+(.+)", line)
        if match:
            headings.append(match.group(1).strip())
    return headings


def source_exists(source: str) -> bool:
    normalized = source.replace("\\", "/")
    candidates = [
        LESSONS_DIR / normalized,
        DOCS_DIR / normalized,
        REPO_ROOT / normalized,
    ]
    return any(path.exists() for path in candidates)


def static_checks(questions: list[dict[str, Any]], index: list[dict[str, Any]]) -> list[CheckResult]:
    results: list[CheckResult] = []

    results.append(CheckResult(
        "goals_file_exists",
        GOALS_PATH.exists(),
        str(GOALS_PATH.relative_to(REPO_ROOT)),
    ))
    results.append(CheckResult(
        "question_bank_exists",
        QA_PATH.exists(),
        str(QA_PATH.relative_to(REPO_ROOT)),
    ))
    results.append(CheckResult(
        "question_bank_has_questions",
        len(questions) >= 30,
        f"{len(questions)} questions",
    ))

    ids = [q.get("id") for q in questions]
    duplicate_ids = sorted({qid for qid in ids if ids.count(qid) > 1})
    results.append(CheckResult(
        "question_ids_unique",
        not duplicate_ids,
        "duplicates: " + ", ".join(duplicate_ids) if duplicate_ids else "all ids unique",
    ))

    malformed = [
        str(q.get("id", f"line {q.get('_line')}"))
        for q in questions
        if not q.get("question")
        or not q.get("required_concepts")
        or not q.get("preferred_sources")
        or not q.get("persona")
    ]
    results.append(CheckResult(
        "question_schema_complete",
        not malformed,
        "malformed: " + ", ".join(malformed[:10]) if malformed else "all questions have required fields",
    ))

    existing_lessons = {p.name for p in LESSONS_DIR.glob("*.md")}
    missing_lessons = [name for name in REQUIRED_LESSONS if name not in existing_lessons]
    results.append(CheckResult(
        "required_lessons_exist",
        not missing_lessons,
        "missing: " + ", ".join(missing_lessons) if missing_lessons else "all required lesson files exist",
    ))

    readme_text = LESSONS_README.read_text(encoding="utf-8") if LESSONS_README.exists() else ""
    missing_from_readme = [
        name for name in REQUIRED_LESSONS if name in existing_lessons and name not in readme_text
    ]
    results.append(CheckResult(
        "required_lessons_linked_from_readme",
        not missing_from_readme,
        "missing from README: " + ", ".join(missing_from_readme) if missing_from_readme else "all existing required lessons are linked",
    ))

    index_pairs = {(entry.get("file"), entry.get("section")) for entry in index}
    missing_index_pairs: list[str] = []
    for lesson in sorted(existing_lessons - {"README.md"}):
        for heading in indexed_markdown_headings(LESSONS_DIR / lesson):
            if (lesson, heading) not in index_pairs:
                missing_index_pairs.append(f"{lesson} > {heading}")
    results.append(CheckResult(
        "lesson_index_matches_headings",
        not missing_index_pairs,
        "missing index entries: " + "; ".join(missing_index_pairs[:12]) if missing_index_pairs else "index covers lesson headings",
    ))

    missing_standard_sections: list[str] = []
    for lesson in sorted(existing_lessons - {"README.md"}):
        headings = {heading.casefold() for heading in all_markdown_headings(LESSONS_DIR / lesson)}
        for section in STANDARD_SECTIONS:
            if section.casefold() not in headings:
                missing_standard_sections.append(f"{lesson} missing {section}")
    results.append(CheckResult(
        "standard_lesson_sections_present",
        not missing_standard_sections,
        "issues: " + "; ".join(missing_standard_sections[:12]) if missing_standard_sections else "standard sections present",
    ))

    missing_source_questions = []
    for question in questions:
        sources = question.get("preferred_sources", [])
        if not any(source_exists(str(source)) for source in sources):
            missing_source_questions.append(str(question.get("id")))
    results.append(CheckResult(
        "qa_questions_have_existing_source",
        not missing_source_questions,
        "no existing preferred source: " + ", ".join(missing_source_questions[:20]) if missing_source_questions else "all questions have at least one existing source",
    ))

    personas = {str(q.get("persona")) for q in questions}
    results.append(CheckResult(
        "qa_personas_cover_junior_and_senior",
        {"junior", "senior"}.issubset(personas),
        "personas: " + ", ".join(sorted(personas)),
    ))

    return results


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.casefold())


def concept_hits(answer: str, concepts: list[str]) -> list[str]:
    normalized = normalize_text(answer)
    hits = []
    for concept in concepts:
        tokens = [token for token in re.split(r"[^a-zA-Z0-9_]+", concept.casefold()) if len(token) >= 4]
        if not tokens:
            continue
        required = max(1, min(len(tokens), 2))
        found = sum(1 for token in tokens if token in normalized)
        if found >= required:
            hits.append(concept)
    return hits


def judge_with_llm(
    question: dict[str, Any],
    answer: str,
    answer_sources: list[dict[str, Any]],
    retries: int,
) -> dict[str, Any]:
    from app.services.chat_service import _call_deepseek, _load_section_content, _read_key

    api_key = _read_key()
    snippets: list[str] = []
    forced_sections: list[tuple[str, str]] = []
    q_text = str(question.get("question", "")).casefold()
    if "tyre" in q_text or "tire" in q_text or "slip" in q_text:
        forced_sections.extend([
            ("Tyre-Model.md", "Slip angle"),
            ("Tyre-Model.md", "Slip ratio"),
            ("Tyre-Model-Deep-Dive.md", "Load sensitivity and base_mu"),
            ("Tyre-Model-Deep-Dive.md", "Combined slip treatment"),
            ("Tyre-Model-Deep-Dive.md", "Validation and guardrails"),
        ])
    if "normal load" in q_text or "normal-load" in q_text or "load transfer" in q_text:
        forced_sections.extend([
            ("Load-Transfer-and-Normal-Loads.md", "Static normal load"),
            ("Load-Transfer-and-Normal-Loads.md", "Aero load split"),
            ("Load-Transfer-and-Normal-Loads.md", "Longitudinal load transfer"),
            ("Load-Transfer-and-Normal-Loads.md", "Physical guardrails"),
            ("Load-Transfer-and-Normal-Loads.md", "Rollover speed cap"),
        ])
    if "brak" in q_text:
        forced_sections.extend([
            ("Braking-Dynamics-and-Deceleration-Budget.md", "Lateral demand consumes braking budget"),
            ("Braking-Dynamics-and-Deceleration-Budget.md", "Aero drag helps braking"),
        ])
    if "validation" in q_text or "falsification" in q_text or "plausible" in q_text or "making plausible" in q_text:
        forced_sections.extend([
            ("Validation-and-Falsification-Workflow.md", "Layer A component contracts"),
            ("Validation-and-Falsification-Workflow.md", "Layer B synthetic maneuvers"),
            ("Validation-and-Falsification-Workflow.md", "Layer C full-lap realism"),
            ("Validation-and-Falsification-Workflow.md", "Falsification examples"),
            ("Validation-and-Falsification-Workflow.md", "Standard hard-gate command"),
            ("Scenario-Separation.md", "Verification checks"),
        ])
    for file, section in forced_sections:
        try:
            content = _load_section_content(file, section)
            snippets.append(f"## {file} > {section}\n{content[:1600]}")
        except Exception:
            continue
    for source in answer_sources[:8]:
        try:
            file = str(source.get("file", ""))
            section = str(source.get("section", ""))
            if (file, section) in forced_sections:
                continue
            content = _load_section_content(file, section)
            snippets.append(f"## {file} > {section}\n{content[:1200]}")
        except Exception:
            continue

    prompt = (
        "You are grading an answer about a Formula Student lap time simulator.\n"
        "Grade only against the expected concepts and the provided source snippets.\n"
        "Return strict JSON with keys: concept_score, grounding_score, critical_unsupported_claim, missing_concepts, reason.\n"
        "concept_score and grounding_score must be numbers from 0 to 1.\n"
        "critical_unsupported_claim must be true only if the answer makes a materially wrong or unsupported simulator claim.\n"
        "Do not require exact wording. Give credit for correct paraphrases and close simulator-specific synonyms. "
        "For example, local point, sampled point, segment-by-segment, frame-by-frame, and point-by-point can satisfy the same concept when the meaning is clear.\n\n"
        f"Question: {question['question']}\n\n"
        f"Expected concepts: {json.dumps(question.get('required_concepts', []))}\n\n"
        f"Source snippets:\n\n{chr(10).join(snippets)[:6000]}\n\n"
        f"Answer:\n{answer[:4000]}"
    )

    last_error = ""
    for attempt in range(1, max(1, retries) + 1):
        try:
            raw = _call_deepseek([{"role": "user", "content": prompt}], api_key, max_tokens=350)
            cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip())
            result = json.loads(cleaned)
            return {
                "concept_score": float(result.get("concept_score", 0.0)),
                "grounding_score": float(result.get("grounding_score", 0.0)),
                "critical_unsupported_claim": bool(result.get("critical_unsupported_claim", True)),
                "missing_concepts": result.get("missing_concepts", []),
                "judge_reason": str(result.get("reason", "")),
                "judge_error": "",
            }
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            if attempt < retries:
                time.sleep(min(2 * attempt, 8))
    hits = concept_hits(answer, [str(c) for c in question.get("required_concepts", [])])
    score = len(hits) / max(1, len(question.get("required_concepts", [])))
    return {
        "concept_score": float(score),
        "grounding_score": 0.0,
        "critical_unsupported_claim": True,
        "missing_concepts": [
            concept for concept in question.get("required_concepts", []) if concept not in hits
        ],
        "judge_reason": "LLM judge failed, fell back to keyword score.",
        "judge_error": last_error,
    }


def run_chat_checks(
    questions: list[dict[str, Any]],
    limit: int | None,
    ids: set[str] | None,
    retries: int = 3,
    judge: str = "llm",
    min_concept_score: float = 0.85,
    min_grounding_score: float = 0.85,
) -> list[dict[str, Any]]:
    sys.path.insert(0, str(REPO_ROOT / "src"))
    from app.services.chat_service import chat

    selected = [q for q in questions if ids is None or str(q.get("id")) in ids]
    selected = selected[:limit] if limit is not None else selected
    rows: list[dict[str, Any]] = []
    for question in selected:
        answer_result: dict[str, Any] | None = None
        last_error = ""
        for attempt in range(1, max(1, retries) + 1):
            try:
                answer_result = chat(str(question["question"]), history=[])
                last_error = ""
                break
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                if attempt < retries:
                    time.sleep(min(2 * attempt, 8))
        if answer_result is None:
            rows.append({
                "id": question["id"],
                "persona": question.get("persona"),
                "topic": question.get("topic"),
                "concept_pass": False,
                "source_pass": False,
                "concept_hits": [],
                "required_concepts": question.get("required_concepts", []),
                "sources": [],
                "preferred_sources": [Path(str(src)).name for src in question.get("preferred_sources", [])],
                "answer": "",
                "error": last_error,
                "concept_score": 0.0,
                "grounding_score": 0.0,
                "critical_unsupported_claim": True,
                "missing_concepts": question.get("required_concepts", []),
                "judge_reason": "No answer generated.",
                "judge_error": "",
            })
            continue
        answer = str(answer_result.get("answer", ""))
        sources = answer_result.get("sources", [])
        source_files = {str(src.get("file")) for src in sources if isinstance(src, dict)}
        preferred_sources = {Path(str(src)).name for src in question.get("preferred_sources", [])}
        hits = concept_hits(answer, [str(c) for c in question.get("required_concepts", [])])
        min_hits = int(question.get("min_required_concepts", max(1, len(question.get("required_concepts", [])) - 1)))
        keyword_concept_pass = len(hits) >= min_hits
        source_pass = bool(source_files & preferred_sources)
        if judge == "llm":
            judge_result = judge_with_llm(question, answer, sources, retries=retries)
            concept_pass = (
                judge_result["concept_score"] >= min_concept_score
                and judge_result["grounding_score"] >= min_grounding_score
                and not judge_result["critical_unsupported_claim"]
            )
        else:
            judge_result = {
                "concept_score": len(hits) / max(1, len(question.get("required_concepts", []))),
                "grounding_score": 1.0 if source_pass else 0.0,
                "critical_unsupported_claim": False,
                "missing_concepts": [
                    concept for concept in question.get("required_concepts", []) if concept not in hits
                ],
                "judge_reason": "Keyword concept matcher.",
                "judge_error": "",
            }
            concept_pass = keyword_concept_pass
        rows.append({
            "id": question["id"],
            "persona": question.get("persona"),
            "topic": question.get("topic"),
            "concept_pass": concept_pass,
            "source_pass": source_pass,
            "concept_hits": hits,
            "required_concepts": question.get("required_concepts", []),
            "sources": sorted(source_files),
            "preferred_sources": sorted(preferred_sources),
            "answer": answer,
            "error": "",
            **judge_result,
        })
    return rows


def write_report(static_results: list[CheckResult], chat_rows: list[dict[str, Any]], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    static_passed = sum(1 for result in static_results if result.passed)
    lines = [
        "# Documentation Eval Report",
        "",
        f"Static checks: {static_passed}/{len(static_results)} passed",
        "",
        "## Static Checks",
        "",
    ]
    for result in static_results:
        status = "PASS" if result.passed else "FAIL"
        lines.append(f"- {status}: {result.name}: {result.detail}")

    if chat_rows:
        concept_passed = sum(1 for row in chat_rows if row["concept_pass"])
        source_passed = sum(1 for row in chat_rows if row["source_pass"])
        critical_count = sum(1 for row in chat_rows if row.get("critical_unsupported_claim"))
        avg_concept_score = sum(float(row.get("concept_score", 0.0)) for row in chat_rows) / len(chat_rows)
        avg_grounding_score = sum(float(row.get("grounding_score", 0.0)) for row in chat_rows) / len(chat_rows)
        lines.extend([
            "",
            "## Chat Checks",
            "",
            f"Concept checks: {concept_passed}/{len(chat_rows)} passed",
            f"Source checks: {source_passed}/{len(chat_rows)} passed",
            f"Average concept score: {avg_concept_score:.3f}",
            f"Average grounding score: {avg_grounding_score:.3f}",
            f"Critical unsupported claims: {critical_count}",
            "",
        ])
        for row in chat_rows:
            concept_status = "PASS" if row["concept_pass"] else "FAIL"
            source_status = "PASS" if row["source_pass"] else "FAIL"
            lines.append(
                f"- {row['id']} ({row['persona']}, {row['topic']}): "
                f"concept={concept_status}, source={source_status}, "
                f"concept_score={float(row.get('concept_score', 0.0)):.2f}, "
                f"grounding_score={float(row.get('grounding_score', 0.0)):.2f}, "
                f"sources={', '.join(row['sources'])}"
            )
            if row.get("error"):
                lines.append(f"  Error: {row['error']}")
            if row.get("judge_error"):
                lines.append(f"  Judge error: {row['judge_error']}")
            if not row["concept_pass"]:
                missing = row.get("missing_concepts", [])
                if missing:
                    lines.append(f"  Missing concepts: {json.dumps(missing)}")
                if row.get("judge_reason"):
                    lines.append(f"  Judge reason: {row['judge_reason']}")

    output.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run simulator documentation evals.")
    parser.add_argument("--mode", choices=["static", "chat", "all"], default="static")
    parser.add_argument("--limit", type=int, default=None, help="Limit chat questions.")
    parser.add_argument("--ids", default="", help="Comma-separated question ids to run.")
    parser.add_argument("--retries", type=int, default=3, help="Retries for each chat question.")
    parser.add_argument("--judge", choices=["llm", "keyword"], default="llm")
    parser.add_argument("--min-concept-score", type=float, default=0.85)
    parser.add_argument("--min-grounding-score", type=float, default=0.85)
    parser.add_argument("--min-pass-rate", type=float, default=0.85)
    parser.add_argument("--min-average-concept-score", type=float, default=0.85)
    parser.add_argument("--min-average-grounding-score", type=float, default=0.85)
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "artifacts" / "docs_eval_report.md",
        help="Markdown report output path.",
    )
    args = parser.parse_args()

    questions = load_jsonl(QA_PATH)
    index = load_index()
    static_results = static_checks(questions, index)
    chat_rows: list[dict[str, Any]] = []

    if args.mode in {"chat", "all"}:
        ids = {part.strip() for part in args.ids.split(",") if part.strip()} or None
        chat_rows = run_chat_checks(
            questions,
            args.limit,
            ids,
            retries=args.retries,
            judge=args.judge,
            min_concept_score=args.min_concept_score,
            min_grounding_score=args.min_grounding_score,
        )

    write_report(static_results, chat_rows, args.output)

    static_passed = sum(1 for result in static_results if result.passed)
    print(f"Static checks: {static_passed}/{len(static_results)} passed")
    if chat_rows:
        concept_passed = sum(1 for row in chat_rows if row["concept_pass"])
        source_passed = sum(1 for row in chat_rows if row["source_pass"])
        print(f"Chat concept checks: {concept_passed}/{len(chat_rows)} passed")
        print(f"Chat source checks: {source_passed}/{len(chat_rows)} passed")
    print(f"Report: {args.output}")

    failed_static = [result for result in static_results if not result.passed]
    if failed_static:
        return 1
    if chat_rows:
        concept_pass_rate = sum(1 for row in chat_rows if row["concept_pass"]) / len(chat_rows)
        source_pass_rate = sum(1 for row in chat_rows if row["source_pass"]) / len(chat_rows)
        avg_concept_score = sum(float(row.get("concept_score", 0.0)) for row in chat_rows) / len(chat_rows)
        avg_grounding_score = sum(float(row.get("grounding_score", 0.0)) for row in chat_rows) / len(chat_rows)
        critical_count = sum(1 for row in chat_rows if row.get("critical_unsupported_claim"))
        if avg_concept_score < args.min_average_concept_score:
            return 1
        if avg_grounding_score < args.min_average_grounding_score:
            return 1
        if source_pass_rate < args.min_pass_rate:
            return 1
        if critical_count > 0:
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
