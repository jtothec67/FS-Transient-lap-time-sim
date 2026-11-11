import copy
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath("src"))

from simulator.util.calcSpeedProfile import forward_pass, backward_pass
from simulator.util.vehicleDynamics import find_vehicle_state_at_point
from track.track import Track, TrackPoint
from vehicle.vehicle import create_vehicle


def _build_track_with_degenerate_segment():
    points = [
        TrackPoint(distance=0.0, x=0.0, y=0.0, z=0.0, curvature=0.0, heading=0.0, elevation_angle=0.0),
        TrackPoint(distance=10.0, x=10.0, y=0.0, z=0.0, curvature=0.0, heading=0.0, elevation_angle=0.0),
        # Degenerate segment: repeated distance.
        TrackPoint(distance=10.0, x=20.0, y=0.0, z=0.0, curvature=0.0, heading=0.0, elevation_angle=0.0),
    ]
    return Track(points, is_closed=False)


class FalsificationAndScenarioContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open("config.json", "r") as f:
            cls.base_config = json.load(f)

    def _vehicle(self, extra_cfg=None):
        cfg = copy.deepcopy(self.base_config)
        cfg.setdefault("ab_testing", {})["model_variant"] = "baseline"
        cfg.setdefault("solver", {})["use_rollover_speed_cap"] = True
        if extra_cfg:
            for k, v in extra_cfg.items():
                cfg[k] = v
        return create_vehicle(cfg), cfg

    def test_solver_invalid_upper_bound_falsification(self):
        vehicle, _ = self._vehicle()
        result = find_vehicle_state_at_point(curvature=0.05, vehicle=vehicle, v_upper_bound_mps=0.0)
        self.assertFalse(result["success"])
        self.assertEqual(result.get("failure_reason"), "invalid_speed_bound")

    def test_propagation_degenerate_segment_falsification(self):
        vehicle, cfg = self._vehicle()
        track = _build_track_with_degenerate_segment()
        point_speeds = [15.0, 15.0, 15.0]

        _, forward_diag = forward_pass(track, vehicle, point_speeds, cfg)
        _, backward_diag = backward_pass(track, vehicle, point_speeds, cfg)

        self.assertIn("degenerate_segment", forward_diag["forward_limiting_mode"])
        self.assertIn("degenerate_segment", backward_diag["backward_limiting_mode"])

    def test_scenario_separation_preserves_base_params(self):
        base_vehicle, _ = self._vehicle()
        scenario_vehicle, _ = self._vehicle(
            {
                "scenario": {
                    "name": "wet_track",
                    "grip_scale": 0.85,
                    "air_density_scale": 1.03,
                }
            }
        )

        # Base parameters should remain unchanged across scenario changes.
        self.assertAlmostEqual(base_vehicle.params.base_mu, scenario_vehicle.params.base_mu, places=12)
        self.assertAlmostEqual(base_vehicle.params.downforce_coefficient, scenario_vehicle.params.downforce_coefficient, places=12)

        # Scenario multipliers must be explicit and active on the scenario vehicle.
        self.assertEqual(scenario_vehicle.scenario_name, "wet_track")
        self.assertAlmostEqual(scenario_vehicle.scenario_grip_scale, 0.85, places=12)
        self.assertAlmostEqual(scenario_vehicle.scenario_air_density_scale, 1.03, places=12)


if __name__ == "__main__":
    unittest.main()
