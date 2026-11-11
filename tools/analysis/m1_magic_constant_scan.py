import argparse
import ast
import math
import os
from typing import Dict, List, Tuple


TARGET_FILES = [
    os.path.join("src", "simulator", "util", "vehicleDynamics.py"),
    os.path.join("src", "simulator", "util", "calcSpeedProfile.py"),
]


# Milestone 1 reviewed literals for core solver/util equations and guards.
# This set is intentionally explicit: any newly introduced literal outside this set
# is treated as undocumented and flagged by the scanner.
APPROVED_LITERALS = {
    -2.0,
    -1.0,
    0.0,
    1.0,
    2.0,
    3.0,
    4.0,
    5.0,
    9.81,
    10.0,
    12.0,
    20.0,
    30.0,
    50.0,
    200.0,
    300.0,
    1500.0,
    0.28,
    0.46,
    0.8,
    0.9,
    0.95,
    0.99,
    1.08,
    1.2,
    1.20,
    1.53,
    1e-2,
    1e-4,
    1e-6,
    1e-9,
    1e-12,
}


def _normalize_literal(value) -> float:
    if isinstance(value, bool):
        raise TypeError("bool is not a numeric literal for this scan")
    return float(value)


def _is_approved(value: float) -> bool:
    for approved in APPROVED_LITERALS:
        if math.isclose(value, float(approved), rel_tol=0.0, abs_tol=1e-12):
            return True
    return False


def _scan_file(file_path: str) -> List[Tuple[int, float, str]]:
    with open(file_path, "r", encoding="utf-8") as f:
        src = f.read()
    tree = ast.parse(src)
    lines = src.splitlines()

    findings: List[Tuple[int, float, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant):
            continue
        if not isinstance(node.value, (int, float)) or isinstance(node.value, bool):
            continue

        value = _normalize_literal(node.value)
        if _is_approved(value):
            continue

        line_no = int(getattr(node, "lineno", 0))
        line_text = lines[line_no - 1].strip() if 1 <= line_no <= len(lines) else ""
        findings.append((line_no, value, line_text))

    findings.sort(key=lambda x: x[0])
    return findings


def run_scan(strict: bool) -> int:
    all_findings: Dict[str, List[Tuple[int, float, str]]] = {}
    for file_path in TARGET_FILES:
        findings = _scan_file(file_path)
        if findings:
            all_findings[file_path] = findings

    print("Milestone 1 magic constant scan")
    print(f"Target files: {', '.join(TARGET_FILES)}")
    print(f"Approved literal count: {len(APPROVED_LITERALS)}")

    if not all_findings:
        print("Result: PASS (no undocumented literals found)")
        return 0

    print("Result: FINDINGS")
    for file_path, findings in all_findings.items():
        print(f"\\n{file_path}")
        for line_no, value, line_text in findings:
            print(f"  L{line_no}: {value} :: {line_text}")

    if strict:
        return 1
    return 0


def main():
    parser = argparse.ArgumentParser(description="Milestone 1 AST scan for undocumented numeric constants")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero when findings are present")
    args = parser.parse_args()
    raise SystemExit(run_scan(strict=bool(args.strict)))


if __name__ == "__main__":
    main()
