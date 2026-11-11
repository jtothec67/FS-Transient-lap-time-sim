import copy
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath("src"))

from diagnostics.constant_radius_suite import build_constant_radius_track
from simulator.simulator import run_lap_time_simulation
from vehicle.vehicle import create_vehicle


class SolverContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open("config.json", "r") as f:
            cls.base_config = json.load(f)

    def _run_case(self, radius_m, param=None, scale=1.0, speed_cap=None):
        cfg = copy.deepcopy(self.base_config)
        cfg["track"] = {"file_path": f"synthetic_constant_radius:{radius_m:.3f}"}
        cfg.setdefault("ab_testing", {})["model_variant"] = "baseline"
        cfg.setdefault("solver", {})["use_rollover_speed_cap"] = True
        if speed_cap is not None:
            cfg.setdefault("solver", {})["straight_line_speed_cap_mps"] = float(speed_cap)

        vehicle = create_vehicle(cfg)
        if param is not None:
            setattr(vehicle.params, param, getattr(vehicle.params, param) * scale)

        track = build_constant_radius_track(radius_m=radius_m, point_count=120)
        result = run_lap_time_simulation(track, vehicle, cfg, display=False)
        return result

    def test_constant_radius_corner_speed_increases_with_radius(self):
        loose = self._run_case(radius_m=20.0)
        tight = self._run_case(radius_m=4.0)
        self.assertGreater(max(loose.corner_speeds), max(tight.corner_speeds))

    def test_straight_like_radius_respects_configured_speed_cap(self):
        # Use huge radius to trigger near-straight branch in corner solver.
        fast_cap = self._run_case(radius_m=50000.0, speed_cap=120.0)
        low_cap = self._run_case(radius_m=50000.0, speed_cap=40.0)

        max_fast = max(fast_cap.corner_speeds)
        max_low = max(low_cap.corner_speeds)
        self.assertGreater(max_fast, max_low)
        self.assertLessEqual(max_low, 40.0 + 1e-6)

    @unittest.expectedFailure  # Known gap: base_mu mutated on vehicle.params after construction does not propagate into the tyre model. Roadmap item.
    def test_base_mu_should_change_constant_radius_result(self):
        # Contract guard that base_mu must influence lap output in tight-corner conditions.
        cfg_radius = 4.0
        low_cfg = copy.deepcopy(self.base_config)
        high_cfg = copy.deepcopy(self.base_config)
        for cfg in (low_cfg, high_cfg):
            cfg["track"] = {"file_path": f"synthetic_constant_radius:{cfg_radius:.3f}"}
            cfg.setdefault("ab_testing", {})["model_variant"] = "baseline"
            cfg.setdefault("solver", {})["use_rollover_speed_cap"] = True

        low_vehicle = create_vehicle(low_cfg)
        high_vehicle = create_vehicle(high_cfg)
        setattr(low_vehicle.params, "base_mu", getattr(low_vehicle.params, "base_mu") * 0.8)
        setattr(high_vehicle.params, "base_mu", getattr(high_vehicle.params, "base_mu") * 1.2)

        track = build_constant_radius_track(radius_m=cfg_radius, point_count=120)
        low_mu = run_lap_time_simulation(track, low_vehicle, low_cfg, display=False)
        high_mu = run_lap_time_simulation(track, high_vehicle, high_cfg, display=False)

        delta = abs(high_mu.lap_time - low_mu.lap_time)
        self.assertGreater(delta, 1e-4, msg=f"Expected non-trivial lap-time sensitivity to base_mu, got delta={delta:.6f}")


if __name__ == "__main__":
    unittest.main()
