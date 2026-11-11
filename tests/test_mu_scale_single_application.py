"""
Regression test: mu_scale is applied exactly once across the lap solver path.

The tyre model (LookupTableTyreModel) embeds base_mu in every force output:
  D = peak_interp(load) * base_mu
So changing base_mu from 1.5 to 3.0 (2x) must produce exactly 2x lateral force,
not 4x (which would indicate double-counting).

Tests cover:
1. Direct tyre model lateral force scales 2x when base_mu doubles.
2. _compute_tyre_lateral_speed_cap scales 2x (no extra mu_scale outside tyre model).
3. _compute_total_force_caps scales 2x (no extra mu_scale).
"""
import copy
import json
import os
import sys
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath("src"))

from simulator.util.calcSpeedProfile import (
    _compute_tyre_lateral_speed_cap,
    _compute_total_force_caps,
)
from vehicle.Tyres.baseTyre import LookupTableTyreModel
from vehicle.vehicle import create_vehicle


def _make_synthetic_tyre_model(base_mu: float) -> LookupTableTyreModel:
    """Build a simple tyre model with known peak forces for controlled scaling tests."""
    lat = pd.DataFrame(
        {
            "Slip Angle [deg]": [-10.0, -5.0, 0.0, 5.0, 10.0,
                                  -10.0, -5.0, 0.0, 5.0, 10.0],
            "Lateral Force [N]": [-1000.0, -800.0, 0.0, 800.0, 1000.0,
                                   -2000.0, -1600.0, 0.0, 1600.0, 2000.0],
            "Normal Load [N]": [500.0] * 5 + [1000.0] * 5,
            "Camber Angle [deg]": [0.0] * 10,
            "Tyre Pressure [kPa]": [200.0] * 10,
            "Temperature [C]": [25.0] * 10,
        }
    )
    lon = pd.DataFrame(
        {
            "Slip Ratio [%]": [-0.2, -0.1, 0.0, 0.1, 0.2,
                                -0.2, -0.1, 0.0, 0.1, 0.2],
            "Longitudinal Force [N]": [-900.0, -700.0, 0.0, 700.0, 900.0,
                                        -1800.0, -1400.0, 0.0, 1400.0, 1800.0],
            "Normal Load [N]": [500.0] * 5 + [1000.0] * 5,
            "Tyre Pressure [kPa]": [200.0] * 10,
            "Temperature [C]": [25.0] * 10,
        }
    )
    return LookupTableTyreModel(lat, lon, base_mu=base_mu, clamp_peak_load_high=True)


class MuScaleSingleApplicationTests(unittest.TestCase):
    """Assert that base_mu scaling is applied exactly once in the lap solver path."""

    def test_tyre_model_lateral_force_scales_linearly_with_base_mu(self):
        """
        Doubling base_mu must double the lateral force from get_lateral_force.
        This confirms the tyre model itself applies mu correctly.
        """
        slip_deg = 8.0
        load = 750.0
        model_lo = _make_synthetic_tyre_model(base_mu=1.5)
        model_hi = _make_synthetic_tyre_model(base_mu=3.0)

        fy_lo = abs(model_lo.get_lateral_force(slip_deg, normal_load=load))
        fy_hi = abs(model_hi.get_lateral_force(slip_deg, normal_load=load))

        self.assertGreater(fy_lo, 0.0, "Baseline lateral force must be nonzero.")
        ratio = fy_hi / fy_lo
        self.assertAlmostEqual(
            ratio, 2.0, delta=0.05,
            msg=f"Lateral force ratio when base_mu doubles: expected 2.0, got {ratio:.4f}. "
                "mu may not be scaling linearly inside the tyre model."
        )

    def test_compute_total_force_caps_scales_linearly_with_base_mu(self):
        """
        Doubling base_mu in the tyre model must double the force caps from
        _compute_total_force_caps. If caps scale by 4x, mu is double-counted.
        """
        load = 750.0

        class FakeVehicle:
            pass

        for base_mu_val in [1.5, 3.0]:
            v = FakeVehicle()
            v.tyre_model = _make_synthetic_tyre_model(base_mu=base_mu_val)
            v.params = type("P", (), {"base_mu": base_mu_val})()
            v.base_mu_reference = base_mu_val
            setattr(v, "base_mu_reference", base_mu_val)

            if base_mu_val == 1.5:
                fx_lo, fy_lo = _compute_total_force_caps(
                    v, front_load=load, rear_load=load,
                    config={}, peak_slip_ratio=0.15
                )
            else:
                fx_hi, fy_hi = _compute_total_force_caps(
                    v, front_load=load, rear_load=load,
                    config={}, peak_slip_ratio=0.15
                )

        self.assertGreater(fy_lo, 0.0)
        self.assertGreater(fx_lo, 0.0)

        lat_ratio = fy_hi / fy_lo
        long_ratio = fx_hi / fx_lo
        self.assertAlmostEqual(
            lat_ratio, 2.0, delta=0.1,
            msg=f"Lateral cap ratio when base_mu doubles: expected 2.0, got {lat_ratio:.4f}. "
                "mu may be double-counted in _compute_total_force_caps."
        )
        self.assertAlmostEqual(
            long_ratio, 2.0, delta=0.1,
            msg=f"Longitudinal cap ratio when base_mu doubles: expected 2.0, got {long_ratio:.4f}. "
                "mu may be double-counted in _compute_total_force_caps."
        )

    def test_compute_tyre_lateral_speed_cap_scales_linearly_with_base_mu(self):
        """
        Doubling base_mu must cause lateral speed cap to scale by sqrt(2), not sqrt(4).
        v_cap = sqrt(a_lat_cap / curvature), and a_lat_cap ~ Fy / m, so if Fy doubles,
        v_cap scales by sqrt(2). A 2x speed cap would indicate 4x force (double-counting).
        """
        curvature = 0.1
        normal_load = 750.0
        config = {}

        class FakeVehicle:
            pass

        for base_mu_val in [1.5, 3.0]:
            v = FakeVehicle()
            v.tyre_model = _make_synthetic_tyre_model(base_mu=base_mu_val)
            v.params = type("P", (), {
                "base_mu": base_mu_val,
                "mass": 320.0,
            })()
            v.base_mu_reference = base_mu_val

            cap = _compute_tyre_lateral_speed_cap(curvature, v, normal_load, config)
            if base_mu_val == 1.5:
                cap_lo = cap
            else:
                cap_hi = cap

        self.assertTrue(np.isfinite(cap_lo) and cap_lo > 0.0)
        self.assertTrue(np.isfinite(cap_hi) and cap_hi > 0.0)

        # v_cap = sqrt(Fy*4/m / k), so v_cap ~ sqrt(Fy) ~ sqrt(base_mu).
        # Expected ratio: sqrt(2) ~ 1.414 when base_mu doubles.
        speed_ratio = cap_hi / cap_lo
        expected_ratio = np.sqrt(2.0)
        self.assertAlmostEqual(
            speed_ratio, expected_ratio, delta=0.05,
            msg=f"Speed cap ratio when base_mu doubles: expected {expected_ratio:.4f}, "
                f"got {speed_ratio:.4f}. If ratio is 2.0 instead of sqrt(2), mu is double-counted."
        )


if __name__ == "__main__":
    unittest.main()
