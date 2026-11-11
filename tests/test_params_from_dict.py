import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from vehicle.vehicle import params_from_dict


SAMPLE = {
    "general": {"name": "Test", "mass": 300.0, "base_mu": 1.4},
    "aerodynamics": {
        "frontal_area": 0.7,
        "drag_coefficient": 0.8,
        "downforce_coefficient": 0.06,
        "aero_cp": 1.1,
    },
    "geometry": {
        "wheelbase": 1.5,
        "front_track_width": 1.2,
        "rear_track_width": 1.2,
        "cog_z": 0.45,
        "cog_longitudinal_pos": 0.5,
        "max_cog_z": 0.55,
    },
    "vehicle_dynamics": {
        "roll_stiffness": 20000.0,
        "suspension_stiffness": 20000,
        "damping_coefficient": 0,
        "max_roll_angle_deg": 8,
    },
    "drivetrain": {
        "wheel_radius": 0.2,
        "final_drive_ratio": 2.5,
        "gear_ratios": [2.5, 1.8],
        "transmission_efficiency": 0.93,
    },
}


def test_params_from_dict_basic_fields():
    p = params_from_dict(SAMPLE)
    assert p.name == "Test"
    assert p.mass == 300.0
    assert p.base_mu == 1.4


def test_params_from_dict_key_rename():
    p = params_from_dict(SAMPLE)
    assert p.aero_centre_of_pressure == 1.1


def test_params_from_dict_gear_ratios():
    p = params_from_dict(SAMPLE)
    assert p.gear_ratios == [2.5, 1.8]


def test_params_from_dict_all_sections():
    p = params_from_dict(SAMPLE)
    assert p.wheelbase == 1.5
    assert p.roll_stiffness == 20000.0
    assert p.transmission_efficiency == 0.93
