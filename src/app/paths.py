import os
import sys
from pathlib import Path, PureWindowsPath


def source_root() -> Path:
    return Path(__file__).resolve().parents[2]


def distribution_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return source_root()


def bundle_root() -> Path:
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass)
        return distribution_root()
    return source_root()


def _first_existing(*candidates: Path) -> Path:
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def app_root() -> Path:
    return distribution_root()


def repo_root() -> Path:
    return _first_existing(
        distribution_root() / "config.json",
        bundle_root() / "config.json",
        source_root() / "config.json",
    ).parent


def config_path() -> Path:
    return _first_existing(
        distribution_root() / "config.json",
        bundle_root() / "config.json",
        source_root() / "config.json",
    )


def parameters_path() -> Path:
    return _first_existing(
        distribution_root() / "parameters.json",
        bundle_root() / "parameters.json",
        source_root() / "parameters.json",
    )


def static_dir() -> Path:
    return _first_existing(
        distribution_root() / "app" / "static",
        bundle_root() / "app" / "static",
        distribution_root() / "src" / "app" / "static",
        source_root() / "src" / "app" / "static",
    )


def lessons_dir() -> Path:
    return _first_existing(
        distribution_root() / "docs" / "lessons",
        bundle_root() / "docs" / "lessons",
        source_root() / "docs" / "lessons",
    )


def workspace_root() -> Path:
    return _first_existing(
        distribution_root() / "src",
        bundle_root() / "src",
        source_root() / "src",
    ).parent


def resolve_repo_path(relative_path: str | Path) -> Path:
    if not relative_path:
        raise ValueError("relative_path must be non-empty")
    raw = str(relative_path)
    # Reject Windows-style absolute paths even when running on POSIX. Path() on Linux
    # treats "C:\\Windows\\System32" as a relative single segment, so the OS-native check
    # below would miss it.
    win = PureWindowsPath(raw)
    if win.is_absolute() or win.drive:
        raise ValueError(f"Absolute paths are not permitted: {relative_path!r}")
    rel = Path(raw)
    if rel.is_absolute() or rel.drive:
        raise ValueError(f"Absolute paths are not permitted: {relative_path!r}")
    parts = rel.parts
    # Check for path separators at the start (e.g., "\etc" on Windows or "/etc" on any OS)
    if parts and parts[0] in ("\\", "/"):
        raise ValueError(f"Absolute paths are not permitted: {relative_path!r}")
    if ".." in parts or any(p.startswith("..") for p in parts):
        raise ValueError(f"Parent-directory traversal is not permitted: {relative_path!r}")
    return _first_existing(
        distribution_root() / rel,
        bundle_root() / rel,
        source_root() / rel,
    )
