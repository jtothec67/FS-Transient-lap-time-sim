"""
Regression test: clamp_peak_load_high prevents unphysical extrapolation.

When clamp_peak_load_high=True, the peak lateral force at loads above the maximum
measured TTC load must not exceed the peak force at the maximum measured load
(within a small numerical tolerance). Without clamping, linear extrapolation would
give ever-increasing peak forces above the measured range, which is unphysical for
real tyres (load sensitivity inverts at high load).

Uses the actual TTC dataset loaded via config.json.
"""
import copy
import json
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.abspath("src"))

from vehicle.Tyres.baseTyre import LookupTableTyreModel
from vehicle.vehicle import create_vehicle


class TyrePeakLoadClampAboveRangeTests(unittest.TestCase):
    """Assert that Fy_peak(Fz > Fz_max_measured) <= Fy_peak(Fz_max_measured) * tolerance."""

    @classmethod
    def setUpClass(cls):
        with open("config.json", "r", encoding="utf-8") as f:
            cls.base_config = json.load(f)
        cfg = copy.deepcopy(cls.base_config)
        vehicle = create_vehicle(cfg)
        cls.tyre_model: LookupTableTyreModel = vehicle.tyre_model  # type: ignore[assignment]

    def test_lateral_peak_does_not_grow_above_max_measured_load(self):
        """
        Fy_peak(Fz) at 2x max measured load must not exceed Fy_peak(Fz_max) * 1.05.
        """
        model = self.tyre_model
        max_measured_load = float(np.nanmax(model._lat_loads))
        overload = max_measured_load * 2.0

        # Representative saturating slip angle: well past peak, so force output is near D.
        saturating_slip_deg = float(np.nanmax(np.abs(model._lat_loads)) * 0.0 + 10.0)

        fy_at_max = abs(model.get_lateral_force(saturating_slip_deg, normal_load=max_measured_load))
        fy_at_overload = abs(model.get_lateral_force(saturating_slip_deg, normal_load=overload))

        tolerance = 1.05  # allow up to 5% above measured peak (small margin for MF shape factors)
        self.assertLessEqual(
            fy_at_overload,
            fy_at_max * tolerance,
            msg=(
                f"Lateral force at 2x max measured load ({fy_at_overload:.1f} N) exceeds "
                f"Fy_peak at max measured load ({fy_at_max:.1f} N) by more than 5%. "
                "clamp_peak_load_high may not be active."
            ),
        )

    def test_longitudinal_peak_does_not_grow_above_max_measured_load(self):
        """
        Fx_peak(Fz) at 2x max measured load must not exceed Fx_peak(Fz_max) * 1.05.
        """
        model = self.tyre_model
        max_measured_load = float(np.nanmax(model._long_loads))
        overload = max_measured_load * 2.0

        saturating_slip_ratio = 0.15  # well past peak for typical FSAE tyre

        fx_at_max = abs(model.get_longitudinal_force(saturating_slip_ratio, normal_load=max_measured_load))
        fx_at_overload = abs(model.get_longitudinal_force(saturating_slip_ratio, normal_load=overload))

        tolerance = 1.05
        self.assertLessEqual(
            fx_at_overload,
            fx_at_max * tolerance,
            msg=(
                f"Longitudinal force at 2x max measured load ({fx_at_overload:.1f} N) exceeds "
                f"Fx_peak at max measured load ({fx_at_max:.1f} N) by more than 5%. "
                "clamp_peak_load_high may not be active."
            ),
        )

    def test_clamp_flag_is_true_on_default_vehicle(self):
        """The default vehicle loaded from config must have clamp_peak_load_high=True."""
        self.assertTrue(
            self.tyre_model.clamp_peak_load_high,
            msg="Default vehicle tyre model should have clamp_peak_load_high=True."
        )

    def test_unclamped_model_does_extrapolate_above_range(self):
        """
        Sanity check: an UNCLAMPED model (clamp_peak_load_high=False) should produce
        higher force at 2x max load than at max load (confirming extrapolation occurs).
        This validates that the clamped tests above are actually testing something meaningful.
        """
        import pandas as pd

        lat = pd.DataFrame(
            {
                "Slip Angle [deg]": [-6.0, -3.0, 0.0, 3.0, 6.0, -6.0, -3.0, 0.0, 3.0, 6.0],
                "Lateral Force [N]": [-80.0, -60.0, 0.0, 60.0, 80.0, -160.0, -120.0, 0.0, 120.0, 160.0],
                "Normal Load [N]": [100.0] * 5 + [200.0] * 5,
                "Camber Angle [deg]": [0.0] * 10,
                "Tyre Pressure [kPa]": [200.0] * 10,
                "Temperature [C]": [25.0] * 10,
            }
        )
        lon = pd.DataFrame(
            {
                "Slip Ratio [%]": [-0.2, -0.1, 0.0, 0.1, 0.2, -0.2, -0.1, 0.0, 0.1, 0.2],
                "Longitudinal Force [N]": [-70.0, -50.0, 0.0, 50.0, 70.0, -140.0, -100.0, 0.0, 100.0, 140.0],
                "Normal Load [N]": [100.0] * 5 + [200.0] * 5,
                "Tyre Pressure [kPa]": [200.0] * 10,
                "Temperature [C]": [25.0] * 10,
            }
        )
        unclamped = LookupTableTyreModel(lat, lon, base_mu=1.0, clamp_peak_load_high=False)
        fy_at_max = abs(unclamped.get_lateral_force(6.0, normal_load=200.0))
        fy_at_overload = abs(unclamped.get_lateral_force(6.0, normal_load=400.0))
        # Without clamping, force at 2x load should be greater.
        self.assertGreater(
            fy_at_overload, fy_at_max,
            msg="Unclamped model should extrapolate to higher force above max measured load."
        )


if __name__ == "__main__":
    unittest.main()
