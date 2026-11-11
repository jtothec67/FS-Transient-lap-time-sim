import copy
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath("src"))

from vehicle.vehicle import create_vehicle


class TyreForceContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open("config.json", "r", encoding="utf-8") as f:
            cls.base_config = json.load(f)

    def _model(self):
        cfg = copy.deepcopy(self.base_config)
        vehicle = create_vehicle(cfg)
        return vehicle.tyre_model

    def test_lateral_force_is_zero_for_zero_or_negative_load(self):
        model = self._model()
        for load in (0.0, -1.0):
            for slip_angle in (0.0, 5.0, 10.0, -10.0):
                fy = model.get_lateral_force(slip_angle, normal_load=load)
                self.assertAlmostEqual(fy, 0.0, places=9)

    def test_longitudinal_force_is_zero_for_zero_or_negative_load(self):
        model = self._model()
        for load in (0.0, -1.0):
            for slip_ratio in (0.0, 0.1, 10.0, -0.2, -10.0):
                fx = model.get_longitudinal_force(slip_ratio, normal_load=load)
                self.assertAlmostEqual(fx, 0.0, places=9)

    def test_combined_forces_are_zero_for_zero_or_negative_load(self):
        model = self._model()
        for load in (0.0, -1.0):
            for slip_angle, slip_ratio in ((0.0, 0.0), (6.0, 0.2), (10.0, 10.0), (-8.0, -10.0)):
                fy, fx = model.get_combined_forces(slip_angle, slip_ratio, normal_load=load)
                self.assertAlmostEqual(fy, 0.0, places=9)
                self.assertAlmostEqual(fx, 0.0, places=9)

    def test_nonzero_load_can_generate_nonzero_force(self):
        model = self._model()
        fy = model.get_lateral_force(8.0, normal_load=200.0)
        fx = model.get_longitudinal_force(0.2, normal_load=200.0)
        self.assertGreater(abs(fy), 1e-6)
        self.assertGreater(abs(fx), 1e-6)


if __name__ == "__main__":
    unittest.main()
