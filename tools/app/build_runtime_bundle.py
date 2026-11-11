from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = REPO_ROOT / "dist" / "LGRSimWorkbenchSource"

RUNTIME_DIRS = [
    Path("src/app"),
    Path("src/simulator"),
    Path("src/track"),
    Path("src/vehicle"),
    Path("datasets/tracks"),
    Path("docs/lessons"),
]

RUNTIME_FILES = [
    Path("src/main.py"),
    Path("config.json"),
    Path("parameters.json"),
    Path("datasets/vehicle/PU_data/Honda_CBR_600RR_RPM_vs_Peak_Power.csv"),
    Path("datasets/vehicle/tyre_data/round_6_12_psi_longit_load_tyredata_parsed.csv"),
    Path("datasets/vehicle/tyre_data/round_8_12_psi_lateral_load_tyredata_parsed.csv"),
    Path("pyproject.toml"),
    Path("requirements.txt"),
    Path("uv.lock"),
    Path("README.md"),
    Path("tools/app/launch_sim_bt.ps1"),
    Path("tools/app/launch_workbench.sh"),
]

OPTIONAL_DIRS = {
    "trackdata": Path("datasets/trackData"),
}

CONFIG_PATH_FIXES = {
    ("tyre_model", "file_path_longit"): "datasets/vehicle/tyre_data/round_6_12_psi_longit_load_tyredata_parsed.csv",
    ("tyre_model", "file_path_lateral"): "datasets/vehicle/tyre_data/round_8_12_psi_lateral_load_tyredata_parsed.csv",
}


def _ignore_copy_patterns(_: str, names: list[str]) -> set[str]:
    ignored: set[str] = set()
    for name in names:
        if name == "__pycache__":
            ignored.add(name)
        elif name.endswith((".pyc", ".pyo")):
            ignored.add(name)
        elif name == ".DS_Store":
            ignored.add(name)
    return ignored


def _copy_path(source_rel: Path, output_root: Path) -> None:
    source = REPO_ROOT / source_rel
    destination = output_root / source_rel

    if not source.exists():
        raise FileNotFoundError(f"Required runtime path does not exist: {source}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        shutil.copytree(source, destination, dirs_exist_ok=True, ignore=_ignore_copy_patterns)
    else:
        shutil.copy2(source, destination)


def _rewrite_bundle_config(output_root: Path) -> None:
    config_path = output_root / "config.json"
    data = json.loads(config_path.read_text(encoding="utf-8"))
    for key_path, value in CONFIG_PATH_FIXES.items():
        cursor = data
        for key in key_path[:-1]:
            cursor = cursor[key]
        cursor[key_path[-1]] = value
    config_path.write_text(json.dumps(data, indent=4) + "\n", encoding="utf-8")


def _bundle_size_mb(output_root: Path) -> float:
    total = sum(path.stat().st_size for path in output_root.rglob("*") if path.is_file())
    return round(total / (1024 * 1024), 2)


def _prune_python_cache(output_root: Path) -> None:
    for cache_dir in output_root.rglob("__pycache__"):
        if cache_dir.is_dir():
            shutil.rmtree(cache_dir)
    for pattern in ("*.pyc", "*.pyo"):
        for compiled_file in output_root.rglob(pattern):
            if compiled_file.is_file():
                compiled_file.unlink()


def _run_smoke_test(output_root: Path) -> dict:
    smoke_script = textwrap.dedent(
        """
        from pathlib import Path
        import sys

        root = Path.cwd()
        sys.path.insert(0, str(root / "src"))

        from app.services.chat_service import _load_index
        from app.services.lap_service import run_lap
        from app.web import create_app

        app = create_app()
        assert app.title == "LGR Sim Workbench"
        assert (root / "tools" / "app" / "launch_sim_bt.ps1").exists()
        assert (root / "tools" / "app" / "launch_workbench.sh").exists()
        assert (root / "docs" / "lessons" / "index.json").exists()

        index = _load_index()
        assert len(index) > 0

        result = run_lap()
        assert result["lap_time_s"] > 0

        print(f"lap_time_s={result['lap_time_s']:.3f}")
        print(f"lesson_sections={len(index)}")
        """
    ).strip()

    env = os.environ.copy()
    env["PYTHONPATH"] = str(output_root / "src")
    env.setdefault("MPLBACKEND", "Agg")

    proc = subprocess.run(
        [sys.executable, "-c", smoke_script],
        cwd=output_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    if proc.returncode != 0:
        raise RuntimeError(
            "Bundle smoke test failed.\n"
            f"stdout:\n{proc.stdout}\n"
            f"stderr:\n{proc.stderr}"
        )

    return {
        "status": "passed",
        "stdout": proc.stdout.strip(),
    }


def _write_manifest(
    output_root: Path,
    include_trackdata: bool,
    zip_created: bool,
    smoke_result: dict | None,
) -> None:
    manifest = {
        "bundle_name": output_root.name,
        "bundle_size_mb": _bundle_size_mb(output_root),
        "included_directories": [str(path).replace("\\", "/") for path in RUNTIME_DIRS],
        "included_files": [str(path).replace("\\", "/") for path in RUNTIME_FILES],
        "optional_includes": {
            "datasets/trackData": include_trackdata,
        },
        "excluded_by_default": [
            ".git",
            ".venv",
            ".pytest_cache",
            ".vscode",
            ".superpowers",
            "ab_test_outputs",
            "artifacts",
            "tests",
            "src/ab_testing",
            "src/diagnostics",
            "tools/analysis",
            "tools/sweeps",
            "tools/tracks",
            "docs/superpowers",
            "docs/parameters",
            "datasets/trackData",
        ],
        "zip_created": zip_created,
        "smoke_test": smoke_result,
    }
    manifest_path = output_root / "bundle_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def build_bundle(
    output_root: Path,
    include_trackdata: bool,
    overwrite: bool,
    run_smoke_test: bool,
    create_zip: bool,
) -> tuple[Path, Path | None]:
    if output_root.exists():
        if not overwrite:
            raise FileExistsError(
                f"Output directory already exists: {output_root}. "
                "Use --overwrite to rebuild it."
            )
        shutil.rmtree(output_root)

    output_root.mkdir(parents=True, exist_ok=True)

    for path in RUNTIME_DIRS:
        _copy_path(path, output_root)
    for path in RUNTIME_FILES:
        _copy_path(path, output_root)

    if include_trackdata:
        _copy_path(OPTIONAL_DIRS["trackdata"], output_root)

    _rewrite_bundle_config(output_root)
    _prune_python_cache(output_root)

    smoke_result = None
    if run_smoke_test:
        smoke_result = _run_smoke_test(output_root)
        _prune_python_cache(output_root)

    _write_manifest(output_root, include_trackdata, create_zip, smoke_result)

    zip_path: Path | None = None
    if create_zip:
        zip_path = output_root.with_suffix(".zip")
        if zip_path.exists() and overwrite:
            zip_path.unlink()
        archive_path = shutil.make_archive(
            str(output_root),
            "zip",
            root_dir=output_root.parent,
            base_dir=output_root.name,
        )
        zip_path = Path(archive_path)

    return output_root, zip_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a slim runtime bundle for the local LGR Sim Workbench."
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Destination folder for the assembled runtime bundle.",
    )
    parser.add_argument(
        "--include-trackdata",
        action="store_true",
        help="Include datasets/trackData in the bundle.",
    )
    parser.add_argument(
        "--skip-smoke-test",
        action="store_true",
        help="Skip the post-build lap-run smoke test.",
    )
    parser.add_argument(
        "--zip",
        action="store_true",
        help="Create a zip file next to the assembled runtime folder.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace any existing output directory and zip file.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_root = Path(args.output_dir).resolve()

    bundle_root, zip_path = build_bundle(
        output_root=output_root,
        include_trackdata=args.include_trackdata,
        overwrite=args.overwrite,
        run_smoke_test=not args.skip_smoke_test,
        create_zip=args.zip,
    )

    print(f"Runtime bundle written to: {bundle_root}")
    print(f"Bundle size: {_bundle_size_mb(bundle_root):.2f} MB")
    if args.include_trackdata:
        print("Included optional dataset: datasets/trackData")
    else:
        print("Excluded optional dataset: datasets/trackData")
    if zip_path is not None:
        print(f"Zip archive written to: {zip_path}")
    print("Smoke test: passed" if not args.skip_smoke_test else "Smoke test: skipped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
