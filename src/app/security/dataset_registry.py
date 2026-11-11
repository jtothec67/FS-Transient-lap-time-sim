"""Allowlist of permitted dataset files. The web layer accepts short IDs only;
the IDs map to concrete paths beneath `datasets/`. Anything else is rejected."""
from __future__ import annotations

from pathlib import Path

from app.paths import repo_root

_TRACKS: dict[str, str] = {
    "FSUK": "datasets/tracks/FSUK.txt",
    "SkidpadF26": "datasets/tracks/SkidpadF26.txt",
    "StraightLineTrack": "datasets/tracks/StraightLineTrack.txt",
}

_TRACK_LABELS: dict[str, str] = {
    "FSUK": "Formula Student UK · Endurance",
    "SkidpadF26": "Skidpad · F26",
    "StraightLineTrack": "Straight Line · Acceleration",
}

_POWERTRAINS: dict[str, str] = {
    "honda_cbr600rr": "datasets/vehicle/PU_data/Honda_CBR_600RR_RPM_vs_Peak_Power.csv",
    "emrax_228_hv": "datasets/vehicle/PU_data/EMRAX_228_HV_CC_P_motor_speed.csv",
}

_POWERTRAIN_LABELS: dict[str, str] = {
    "honda_cbr600rr": "Honda CBR 600RR · RPM vs Peak Power",
    "emrax_228_hv": "EMRAX 228 HV CC · Power vs Motor Speed",
}

_TYRE_LATERAL: dict[str, str] = {
    "round_8_12psi": "datasets/vehicle/tyre_data/round_8_12_psi_lateral_load_tyredata_parsed.csv",
}

_TYRE_LONGITUDINAL: dict[str, str] = {
    "round_6_12psi": "datasets/vehicle/tyre_data/round_6_12_psi_longit_load_tyredata_parsed.csv",
}

_TYRE_LATERAL_LABELS: dict[str, str] = {
    "round_8_12psi": "Hoosier 16x6.0-10 R25B · TTC R8 · 12 PSI",
}

_TYRE_LONGITUDINAL_LABELS: dict[str, str] = {
    "round_6_12psi": "FSAE TTC R6 · 12 PSI",
}


def _lookup(table: dict[str, str], dataset_id: str, kind: str) -> Path:
    if not isinstance(dataset_id, str) or not dataset_id:
        raise ValueError(f"{kind} id must be a non-empty string")
    if dataset_id not in table:
        raise ValueError(f"Unknown {kind} id: {dataset_id!r}")
    candidate = repo_root() / table[dataset_id]
    resolved = candidate.resolve()
    root = repo_root().resolve()
    if root not in resolved.parents and resolved != root:
        raise ValueError(f"Resolved {kind} path escapes repo root")
    return resolved


def get_track_path(track_id: str) -> Path:
    return _lookup(_TRACKS, track_id, "track")


def get_tyre_lateral_path(dataset_id: str) -> Path:
    return _lookup(_TYRE_LATERAL, dataset_id, "tyre lateral")


def get_tyre_longitudinal_path(dataset_id: str) -> Path:
    return _lookup(_TYRE_LONGITUDINAL, dataset_id, "tyre longitudinal")


def list_track_ids() -> list[str]:
    return sorted(_TRACKS.keys())


def list_tyre_lateral_ids() -> list[str]:
    return sorted(_TYRE_LATERAL.keys())


def list_tyre_longitudinal_ids() -> list[str]:
    return sorted(_TYRE_LONGITUDINAL.keys())


def list_tracks() -> list[dict[str, str]]:
    return [
        {"id": k, "label": _TRACK_LABELS.get(k, k)}
        for k in sorted(_TRACKS.keys())
    ]


def list_powertrains() -> list[dict[str, str]]:
    return [
        {"id": k, "label": _POWERTRAIN_LABELS.get(k, k)}
        for k in sorted(_POWERTRAINS.keys())
    ]


def lookup_powertrain_label_by_path(rel_or_abs_path: str) -> str | None:
    """Reverse lookup. Given a config path, return the human label if the path
    matches a registered powertrain. Returns None if no match."""
    if not rel_or_abs_path:
        return None
    target = rel_or_abs_path.replace("\\", "/").rsplit("/", 1)[-1].lower()
    for pid, rel in _POWERTRAINS.items():
        if rel.replace("\\", "/").rsplit("/", 1)[-1].lower() == target:
            return _POWERTRAIN_LABELS.get(pid, pid)
    return None


def lookup_track_id_by_path(rel_or_abs_path: str) -> str | None:
    if not rel_or_abs_path:
        return None
    target = rel_or_abs_path.replace("\\", "/").rsplit("/", 1)[-1].lower()
    for tid, rel in _TRACKS.items():
        if rel.replace("\\", "/").rsplit("/", 1)[-1].lower() == target:
            return tid
    return None


def lookup_tyre_lateral_id_by_path(rel_or_abs_path: str) -> str | None:
    if not rel_or_abs_path:
        return None
    target = rel_or_abs_path.replace("\\", "/").rsplit("/", 1)[-1].lower()
    for tid, rel in _TYRE_LATERAL.items():
        if rel.replace("\\", "/").rsplit("/", 1)[-1].lower() == target:
            return tid
    return None


def lookup_tyre_longitudinal_id_by_path(rel_or_abs_path: str) -> str | None:
    if not rel_or_abs_path:
        return None
    target = rel_or_abs_path.replace("\\", "/").rsplit("/", 1)[-1].lower()
    for tid, rel in _TYRE_LONGITUDINAL.items():
        if rel.replace("\\", "/").rsplit("/", 1)[-1].lower() == target:
            return tid
    return None


def get_track_label(track_id: str) -> str:
    return _TRACK_LABELS.get(track_id, track_id)


def get_tyre_lateral_label(dataset_id: str) -> str:
    return _TYRE_LATERAL_LABELS.get(dataset_id, dataset_id)


def get_tyre_longitudinal_label(dataset_id: str) -> str:
    return _TYRE_LONGITUDINAL_LABELS.get(dataset_id, dataset_id)


def list_tyre_lateral() -> list[dict[str, str]]:
    return [
        {"id": k, "label": _TYRE_LATERAL_LABELS.get(k, k)}
        for k in sorted(_TYRE_LATERAL.keys())
    ]


def list_tyre_longitudinal() -> list[dict[str, str]]:
    return [
        {"id": k, "label": _TYRE_LONGITUDINAL_LABELS.get(k, k)}
        for k in sorted(_TYRE_LONGITUDINAL.keys())
    ]
