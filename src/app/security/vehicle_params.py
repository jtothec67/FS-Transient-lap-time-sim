"""Explicit allowlist of vehicle parameters that may be overridden via the API.
Replaces the prior `hasattr` check, which accepted dunder names and any private
attribute that happened to exist on `vehicle.params`."""
from __future__ import annotations

_ALIASES: dict[str, str] = {
    "aero_cp": "aero_centre_of_pressure",
}

_OVERRIDABLE: frozenset[str] = frozenset({
    "mass",
    "base_mu",
    "frontal_area",
    "drag_coefficient",
    "downforce_coefficient",
    "aero_centre_of_pressure",
    "wheelbase",
    "front_track_width",
    "rear_track_width",
    "cog_z",
    "cog_longitudinal_pos",
    "wheel_radius",
    "final_drive_ratio",
    "transmission_efficiency",
    "roll_stiffness",
})


def canonical_or_reject(name: str) -> str:
    """Return the canonical attribute name for `name`, or raise ValueError if
    `name` is not in the allowlist. Resolves aliases like `aero_cp`."""
    if not isinstance(name, str) or not name:
        raise ValueError("parameter name must be a non-empty string")
    canonical = _ALIASES.get(name, name)
    if canonical not in _OVERRIDABLE:
        raise ValueError(f"Parameter {name!r} is not overridable")
    return canonical


def is_overridable(name: str) -> bool:
    try:
        canonical_or_reject(name)
        return True
    except ValueError:
        return False


def list_overridable_params() -> list[str]:
    return sorted(_OVERRIDABLE)
