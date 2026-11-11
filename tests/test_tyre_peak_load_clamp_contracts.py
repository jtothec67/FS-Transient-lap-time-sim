import os
import sys
import unittest

import pandas as pd

sys.path.insert(0, os.path.abspath("src"))

from vehicle.Tyres.baseTyre import LookupTableTyreModel


class TyrePeakLoadClampContractTests(unittest.TestCase):
    def _make_model(self, clamp_peak_load_high, base_mu=1.0):
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
        return LookupTableTyreModel(
            lat,
            lon,
            base_mu=base_mu,
            clamp_peak_load_high=clamp_peak_load_high,
        )

    def test_clamped_variant_caps_high_load_lateral_peak_growth(self):
        baseline = self._make_model(clamp_peak_load_high=False)
        clamped = self._make_model(clamp_peak_load_high=True)

        fy_at_max_measured = clamped.get_lateral_force(6.0, normal_load=200.0)
        fy_high_load_clamped = clamped.get_lateral_force(6.0, normal_load=400.0)
        fy_high_load_baseline = baseline.get_lateral_force(6.0, normal_load=400.0)

        self.assertAlmostEqual(fy_high_load_clamped, fy_at_max_measured, places=8)
        self.assertGreater(abs(fy_high_load_baseline), abs(fy_high_load_clamped))

    def test_clamped_variant_caps_high_load_longitudinal_peak_growth(self):
        baseline = self._make_model(clamp_peak_load_high=False)
        clamped = self._make_model(clamp_peak_load_high=True)

        fx_at_max_measured = clamped.get_longitudinal_force(0.2, normal_load=200.0)
        fx_high_load_clamped = clamped.get_longitudinal_force(0.2, normal_load=400.0)
        fx_high_load_baseline = baseline.get_longitudinal_force(0.2, normal_load=400.0)

        self.assertAlmostEqual(fx_high_load_clamped, fx_at_max_measured, places=8)
        self.assertGreater(abs(fx_high_load_baseline), abs(fx_high_load_clamped))

    def test_clamped_variant_preserves_zero_load_invariant(self):
        clamped = self._make_model(clamp_peak_load_high=True)
        fy = clamped.get_lateral_force(10.0, normal_load=0.0)
        fx = clamped.get_longitudinal_force(0.2, normal_load=0.0)
        self.assertAlmostEqual(fy, 0.0, places=9)
        self.assertAlmostEqual(fx, 0.0, places=9)

    def test_base_mu_is_scaled_against_dataset_reference_mu(self):
        model = self._make_model(clamp_peak_load_high=True, base_mu=1.4)
        diag = model.get_domain_diagnostics()

        self.assertAlmostEqual(diag["lateral_peak_mu_reference"], 0.8, places=9)
        self.assertAlmostEqual(diag["longitudinal_peak_mu_reference"], 0.7, places=9)
        self.assertAlmostEqual(diag["lateral_base_mu_scale"], 1.4 / 0.8, places=9)
        self.assertAlmostEqual(diag["longitudinal_base_mu_scale"], 1.4 / 0.7, places=9)


if __name__ == "__main__":
    unittest.main()
