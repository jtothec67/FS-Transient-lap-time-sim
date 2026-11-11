import os
import sys
import unittest

import pandas as pd

sys.path.insert(0, os.path.abspath("src"))

from vehicle.Tyres.baseTyre import LookupTableTyreModel


class TyreValidityDomainContractTests(unittest.TestCase):
    def _make_model(self, clamp_peak_load_high=False):
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
                "Slip Ratio [%]": [-20.0, -10.0, 0.0, 10.0, 20.0, -20.0, -10.0, 0.0, 10.0, 20.0],
                "Longitudinal Force [N]": [-70.0, -50.0, 0.0, 50.0, 70.0, -140.0, -100.0, 0.0, 100.0, 140.0],
                "Normal Load [N]": [100.0] * 5 + [200.0] * 5,
                "Tyre Pressure [kPa]": [200.0] * 10,
                "Temperature [C]": [25.0] * 10,
            }
        )
        return LookupTableTyreModel(
            lat,
            lon,
            base_mu=1.0,
            clamp_peak_load_high=clamp_peak_load_high,
        )

    def test_domain_counters_increment_for_out_of_domain_calls(self):
        model = self._make_model(clamp_peak_load_high=False)

        # In-domain call should not increment out-of-domain counters.
        model.get_lateral_force(3.0, normal_load=150.0)

        # Out-of-domain slip and load requests.
        model.get_lateral_force(12.0, normal_load=260.0)
        model.get_longitudinal_force(0.8, normal_load=260.0)
        model.get_combined_forces(12.0, 0.8, normal_load=260.0)

        diag = model.get_domain_diagnostics()
        self.assertGreaterEqual(diag["lateral_out_of_domain_slip"], 1)
        self.assertGreaterEqual(diag["lateral_out_of_domain_load"], 1)
        self.assertGreaterEqual(diag["longitudinal_out_of_domain_slip"], 1)
        self.assertGreaterEqual(diag["longitudinal_out_of_domain_load"], 1)
        self.assertGreaterEqual(diag["combined_out_of_domain_any"], 1)
        self.assertGreater(diag["out_of_domain_total"], 0)

    def test_clamp_counter_increments_when_high_load_is_clamped(self):
        model = self._make_model(clamp_peak_load_high=True)
        model.get_lateral_force(5.0, normal_load=300.0)
        model.get_longitudinal_force(0.2, normal_load=300.0)

        diag = model.get_domain_diagnostics()
        self.assertGreaterEqual(diag["clamped_high_load_lateral"], 1)
        self.assertGreaterEqual(diag["clamped_high_load_longitudinal"], 1)

    def test_reset_domain_diagnostics_zeros_counters(self):
        model = self._make_model(clamp_peak_load_high=True)
        model.get_lateral_force(12.0, normal_load=300.0)
        self.assertGreater(model.get_domain_diagnostics()["out_of_domain_total"], 0)

        model.reset_domain_diagnostics()
        diag = model.get_domain_diagnostics()
        self.assertEqual(diag["out_of_domain_total"], 0)
        self.assertEqual(diag["lateral_calls"], 0)
        self.assertEqual(diag["longitudinal_calls"], 0)
        self.assertEqual(diag["combined_calls"], 0)


if __name__ == "__main__":
    unittest.main()
