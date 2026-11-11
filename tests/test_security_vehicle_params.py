import pytest

from app.security.vehicle_params import canonical_or_reject, is_overridable, list_overridable_params


def test_known_param_passes():
    assert canonical_or_reject("mass") == "mass"


def test_alias_is_canonicalised():
    assert canonical_or_reject("aero_cp") == "aero_centre_of_pressure"


def test_unknown_param_rejected():
    with pytest.raises(ValueError):
        canonical_or_reject("__class__")
    with pytest.raises(ValueError):
        canonical_or_reject("not_a_real_param")


def test_dunder_attempts_rejected():
    for hostile in ["__init__", "__class__", "_private", "params.__dict__"]:
        with pytest.raises(ValueError):
            canonical_or_reject(hostile)


def test_is_overridable_matches_canonical_or_reject():
    assert is_overridable("mass")
    assert not is_overridable("__class__")


def test_list_overridable_includes_expected_subset():
    names = list_overridable_params()
    for required in ["mass", "wheelbase", "aero_centre_of_pressure", "transmission_efficiency", "final_drive_ratio", "wheel_radius"]:
        assert required in names


def test_overridable_names_match_real_dataclass_attributes():
    """Defence: every name in the allowlist must be a real attribute of
    `vehicle_parameters`. If this test fails, the allowlist is out of sync
    with the dataclass and `setattr` will succeed on an attribute that the
    simulator does not actually read."""
    from dataclasses import fields
    from vehicle.vehicle import vehicle_parameters
    real_attrs = {f.name for f in fields(vehicle_parameters)}
    for name in list_overridable_params():
        assert name in real_attrs, f"{name!r} is in the allowlist but not on vehicle_parameters"
