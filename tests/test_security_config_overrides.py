import pytest

from app.security.config_overrides import ConfigOverrides, build_config


def _base_config():
    return {
        "powertrain": {"powertrain": "datasets/vehicle/PU_data/Honda_CBR_600RR_RPM_vs_Peak_Power.csv", "type": "lookup"},
        "track": {"file_path": "datasets/tracks/FSUK.txt"},
        "tyre_model": {
            "file_path_longit": "datasets/vehicle/tyre_data/round_6_12_psi_longit_load_tyredata_parsed.csv",
            "file_path_lateral": "datasets/vehicle/tyre_data/round_8_12_psi_lateral_load_tyredata_parsed.csv",
            "type": "lookup",
        },
        "vehicle_parameters": "parameters.json",
        "debug_mode": False,
        "full_telemetry_mode": True,
        "solver": {"use_rollover_speed_cap": True, "max_brake_decel_g": 2.0},
        "ambient_conditions": {"air_density": 1.225},
    }


def test_build_config_with_no_overrides_returns_resolved_base():
    cfg = build_config(_base_config(), ConfigOverrides())
    assert cfg["track"]["file_path"].endswith("FSUK.txt")
    assert cfg["debug_mode"] is False


def test_build_config_with_track_id_swaps_track_file():
    cfg = build_config(_base_config(), ConfigOverrides(track_id="SkidpadF26"))
    assert cfg["track"]["file_path"].endswith("SkidpadF26.txt")


def test_build_config_with_unknown_track_id_raises():
    with pytest.raises(ValueError):
        build_config(_base_config(), ConfigOverrides(track_id="not_a_real_track"))


def test_build_config_always_forces_debug_mode_off():
    base = _base_config()
    base["debug_mode"] = True
    cfg = build_config(base, ConfigOverrides())
    assert cfg["debug_mode"] is False


def test_build_config_accepts_ambient_air_density_override():
    cfg = build_config(_base_config(), ConfigOverrides(air_density=1.0))
    assert cfg["ambient_conditions"]["air_density"] == 1.0


def test_build_config_air_density_rejects_out_of_range():
    with pytest.raises(ValueError):
        ConfigOverrides(air_density=-1.0)
    with pytest.raises(ValueError):
        ConfigOverrides(air_density=999.0)


def test_build_config_accepts_max_brake_decel_override():
    cfg = build_config(_base_config(), ConfigOverrides(max_brake_decel_g=1.5))
    assert cfg["solver"]["max_brake_decel_g"] == 1.5


def test_build_config_max_brake_decel_rejects_out_of_range():
    with pytest.raises(ValueError):
        ConfigOverrides(max_brake_decel_g=-0.1)
    with pytest.raises(ValueError):
        ConfigOverrides(max_brake_decel_g=10.0)


def test_build_config_does_not_mutate_base():
    base = _base_config()
    base_copy = dict(base)
    build_config(base, ConfigOverrides(track_id="SkidpadF26"))
    assert base == base_copy
