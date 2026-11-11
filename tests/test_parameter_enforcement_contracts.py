import copy
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath("src"))

from simulator.util.calcSpeedProfile import _compute_normal_loads_for_longitudinal
from vehicle.vehicle import create_vehicle


class ParameterEnforcementContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open("config.json", "r") as f:
            cls.base_config = json.load(f)

    def _vehicle(self, param_overrides=None):
        cfg = copy.deepcopy(self.base_config)
        cfg.setdefault("ab_testing", {})["model_variant"] = "b1"
        vehicle = create_vehicle(cfg)
        if param_overrides:
            for k, v in param_overrides.items():
                setattr(vehicle.params, k, v)
        return vehicle, cfg

    @staticmethod
    def _force_constant_engine_torque(vehicle, torque_nm=100.0):
        vehicle.power_unit.get_torque = lambda rpm, throttle=1.0: float(torque_nm)

    def test_drag_coefficient_monotonic_drag_force(self):
        vehicle_low, _ = self._vehicle({"drag_coefficient": 0.6})
        vehicle_high, _ = self._vehicle({"drag_coefficient": 1.1})

        v = 20.0
        f_low = vehicle_low.compute_aero_drag(v)
        f_high = vehicle_high.compute_aero_drag(v)
        self.assertGreater(f_high, f_low)

    def test_frontal_area_monotonic_drag_and_downforce(self):
        # compute_aero_drag still uses frontal_area directly.
        # compute_downforce uses CLA_m2 = Cl * A; both frontal_area and CLA_m2 must change together.
        vehicle_low, _ = self._vehicle({"frontal_area": 0.6, "CLA_m2": 0.6 * 0.07})
        vehicle_high, _ = self._vehicle({"frontal_area": 0.9, "CLA_m2": 0.9 * 0.07})

        v = 20.0
        self.assertGreater(vehicle_high.compute_aero_drag(v), vehicle_low.compute_aero_drag(v))
        self.assertGreater(vehicle_high.compute_downforce(v), vehicle_low.compute_downforce(v))

    def test_downforce_coefficient_monotonic_downforce(self):
        # compute_downforce uses CLA_m2 (Cl * A). Changing the legacy downforce_coefficient field
        # no longer affects downforce directly — set CLA_m2 instead.
        frontal_area = 0.75  # from parameters.json
        vehicle_low, _ = self._vehicle({"CLA_m2": 0.04 * frontal_area})
        vehicle_high, _ = self._vehicle({"CLA_m2": 0.12 * frontal_area})

        v = 20.0
        self.assertGreater(vehicle_high.compute_downforce(v), vehicle_low.compute_downforce(v))

    def test_aero_cp_shifts_front_rear_load_distribution(self):
        vehicle_front, cfg = self._vehicle({"aero_centre_of_pressure": 0.3})
        vehicle_rear, _ = self._vehicle({"aero_centre_of_pressure": 1.3})

        v = 25.0
        front_cp_state = _compute_normal_loads_for_longitudinal(vehicle_front, v_car=v, a_long=0.0, config=cfg)
        rear_cp_state = _compute_normal_loads_for_longitudinal(vehicle_rear, v_car=v, a_long=0.0, config=cfg)

        self.assertGreater(front_cp_state["front_per_tyre"], rear_cp_state["front_per_tyre"])
        self.assertGreater(rear_cp_state["rear_per_tyre"], front_cp_state["rear_per_tyre"])

        # Total normal load should stay consistent for fixed speed and mass.
        self.assertAlmostEqual(front_cp_state["total_normal_load"], rear_cp_state["total_normal_load"], places=8)

    def test_transmission_efficiency_monotonic_wheel_torque(self):
        vehicle_low, _ = self._vehicle({"transmission_efficiency": 0.80})
        vehicle_high, _ = self._vehicle({"transmission_efficiency": 0.95})
        self._force_constant_engine_torque(vehicle_low)
        self._force_constant_engine_torque(vehicle_high)

        rpm = 8000.0
        gear_ratio = 2.0
        t_low = vehicle_low.compute_wheel_torque(rpm, gear_ratio)
        t_high = vehicle_high.compute_wheel_torque(rpm, gear_ratio)
        self.assertGreater(t_high, t_low)

    def test_final_drive_ratio_monotonic_wheel_torque(self):
        vehicle_low, _ = self._vehicle({"final_drive_ratio": 3.6})
        vehicle_high, _ = self._vehicle({"final_drive_ratio": 4.2})
        self._force_constant_engine_torque(vehicle_low)
        self._force_constant_engine_torque(vehicle_high)

        rpm = 8000.0
        gear_ratio = 2.0
        t_low = vehicle_low.compute_wheel_torque(rpm, gear_ratio)
        t_high = vehicle_high.compute_wheel_torque(rpm, gear_ratio)
        self.assertGreater(t_high, t_low)

    def test_wheel_radius_monotonic_traction_force(self):
        vehicle_small_r, _ = self._vehicle({"wheel_radius": 0.20})
        vehicle_large_r, _ = self._vehicle({"wheel_radius": 0.28})
        self._force_constant_engine_torque(vehicle_small_r)
        self._force_constant_engine_torque(vehicle_large_r)

        rpm = 8000.0
        gear_ratio = 2.0
        t_small = vehicle_small_r.compute_wheel_torque(rpm, gear_ratio)
        t_large = vehicle_large_r.compute_wheel_torque(rpm, gear_ratio)
        f_small = t_small / vehicle_small_r.params.wheel_radius
        f_large = t_large / vehicle_large_r.params.wheel_radius
        self.assertGreater(f_small, f_large)

    def test_gear_ratio_monotonic_wheel_torque(self):
        vehicle, _ = self._vehicle()
        self._force_constant_engine_torque(vehicle)

        rpm = 8000.0
        t_low = vehicle.compute_wheel_torque(rpm, gear_ratio=1.8)
        t_high = vehicle.compute_wheel_torque(rpm, gear_ratio=2.6)
        self.assertGreater(t_high, t_low)

    def test_gear_ratio_stack_changes_optimal_gear(self):
        vehicle, _ = self._vehicle({"gear_ratios": [1.8, 2.2, 2.7]})
        self._force_constant_engine_torque(vehicle)

        optimal = vehicle.select_optimal_gear(v_car=12.0)
        self.assertEqual(optimal, 2.7)


if __name__ == "__main__":
    unittest.main()
