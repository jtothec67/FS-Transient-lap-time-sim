"""
Regression test: cog_longitudinal_pos as front mass fraction.

Canonical definition: cog_longitudinal_pos = fraction of total mass carried by the
front axle in static conditions (dimensionless, 0 to 1). Equivalently, this equals
the distance from the rear axle to the CoG divided by the wheelbase (l_r / L).

With cog_longitudinal_pos = 0.6 and mass = 320 kg:
  Front axle static load = 0.6 * 320 * 9.81 = 1883.52 N
  Rear axle static load  = 0.4 * 320 * 9.81 = 1255.68 N
"""
import copy
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath("src"))

from simulator.util.calcSpeedProfile import _compute_normal_loads_for_longitudinal
from vehicle.vehicle import create_vehicle


class CogLongitudinalPosCanonicalTests(unittest.TestCase):
    """Assert that cog_longitudinal_pos is treated consistently as front mass fraction."""

    @classmethod
    def setUpClass(cls):
        with open("config.json", "r", encoding="utf-8") as f:
            cls.base_config = json.load(f)

    def _make_vehicle_with_cog(self, cog_longitudinal_pos: float, mass: float = 320.0):
        """Create a vehicle with the specified cog_longitudinal_pos and mass."""
        import json as _json
        import copy as _copy

        cfg = _copy.deepcopy(self.base_config)
        params_path = cfg.get("vehicle_parameters", "parameters.json")
        with open(params_path, "r", encoding="utf-8") as f:
            params = _json.load(f)

        params["geometry"]["cog_longitudinal_pos"] = cog_longitudinal_pos
        params["general"]["mass"] = mass

        # Write to a temp location by monkey-patching create_vehicle
        # Instead, use create_vehicle with a config that embeds the params dict.
        cfg["vehicle_parameters"] = params_path
        vehicle = create_vehicle(cfg)
        # Override the params directly for this test
        vehicle.params.cog_longitudinal_pos = cog_longitudinal_pos
        vehicle.params.mass = mass
        vehicle.weight = mass * 9.81
        return vehicle

    def test_static_front_axle_load_matches_front_mass_fraction(self):
        """
        With cog_longitudinal_pos=0.6 and mass=320 kg, front axle static load must equal
        0.6 * 320 * 9.81 = 1883.52 N (to within 1 N tolerance).
        """
        vehicle = self._make_vehicle_with_cog(cog_longitudinal_pos=0.6, mass=320.0)

        # Use a minimal config that selects baseline (no load transfer variant).
        cfg = {"ab_testing": {"model_variant": "baseline"}}
        loads = _compute_normal_loads_for_longitudinal(vehicle, v_car=0.0, a_long=0.0, config=cfg)

        # Baseline returns static load per tyre = mass * g / 4
        # For checking canonical, we verify the front_frac interpretation via the b1 variant.
        cfg_b1 = {"ab_testing": {"model_variant": "b1"}}
        loads_b1 = _compute_normal_loads_for_longitudinal(vehicle, v_car=0.0, a_long=0.0, config=cfg_b1)

        expected_front_axle_N = 0.6 * 320.0 * 9.81   # 1883.52 N
        expected_rear_axle_N  = 0.4 * 320.0 * 9.81   # 1255.68 N

        actual_front_axle_N = loads_b1["front_per_tyre"] * 2.0
        actual_rear_axle_N  = loads_b1["rear_per_tyre"]  * 2.0

        self.assertAlmostEqual(
            actual_front_axle_N, expected_front_axle_N, delta=1.0,
            msg=f"Front axle load: expected {expected_front_axle_N:.2f} N, got {actual_front_axle_N:.2f} N"
        )
        self.assertAlmostEqual(
            actual_rear_axle_N, expected_rear_axle_N, delta=1.0,
            msg=f"Rear axle load: expected {expected_rear_axle_N:.2f} N, got {actual_rear_axle_N:.2f} N"
        )

    def test_front_plus_rear_equals_total_weight(self):
        """Front + rear axle loads must sum to total weight."""
        vehicle = self._make_vehicle_with_cog(cog_longitudinal_pos=0.516, mass=320.0)
        cfg_b1 = {"ab_testing": {"model_variant": "b1"}}
        loads = _compute_normal_loads_for_longitudinal(vehicle, v_car=0.0, a_long=0.0, config=cfg_b1)

        total = loads["front_per_tyre"] * 2.0 + loads["rear_per_tyre"] * 2.0
        expected_total = 320.0 * 9.81
        self.assertAlmostEqual(total, expected_total, delta=1.0,
            msg=f"Total axle load {total:.2f} N does not match weight {expected_total:.2f} N")

    def test_higher_cog_pos_gives_more_front_load(self):
        """Increasing cog_longitudinal_pos must increase front axle load."""
        cfg_b1 = {"ab_testing": {"model_variant": "b1"}}

        v_lo = self._make_vehicle_with_cog(cog_longitudinal_pos=0.4)
        v_hi = self._make_vehicle_with_cog(cog_longitudinal_pos=0.6)

        loads_lo = _compute_normal_loads_for_longitudinal(v_lo, v_car=0.0, a_long=0.0, config=cfg_b1)
        loads_hi = _compute_normal_loads_for_longitudinal(v_hi, v_car=0.0, a_long=0.0, config=cfg_b1)

        self.assertGreater(
            loads_hi["front_per_tyre"], loads_lo["front_per_tyre"],
            msg="Higher cog_longitudinal_pos should give more front axle load."
        )


if __name__ == "__main__":
    unittest.main()
