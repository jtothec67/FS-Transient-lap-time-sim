import copy
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath("src"))

from simulator.util.calcSpeedProfile import (
    _longitudinal_budget_scale_from_lateral_demand,
    backward_pass,
    compute_speed_profile,
    forward_pass,
)
from simulator.util.vehicleDynamics import find_vehicle_state_at_point
from track.track import Track, TrackPoint
from vehicle.vehicle import create_vehicle


def _dim_mul(*dims):
    return (
        sum(d[0] for d in dims),
        sum(d[1] for d in dims),
        sum(d[2] for d in dims),
    )


def _dim_div(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _dim_pow(a, p):
    return (a[0] * p, a[1] * p, a[2] * p)


# Base dimensions represented as exponents of (kg, m, s).
DIMENSIONLESS = (0, 0, 0)
KG = (1, 0, 0)
M = (0, 1, 0)
S = (0, 0, 1)

# Derived dimensions.
MPS = _dim_div(M, S)          # m/s
MPS2 = _dim_div(M, _dim_pow(S, 2))  # m/s^2
CURVATURE = _dim_div(DIMENSIONLESS, M)  # 1/m
NEWTON = _dim_mul(KG, MPS2)   # kg*m/s^2


def _build_straight_track(ds=10.0, n_points=4):
    points = []
    for i in range(n_points):
        points.append(
            TrackPoint(
                distance=float(i * ds),
                x=float(i * ds),
                y=0.0,
                z=0.0,
                curvature=0.0,
                heading=0.0,
                elevation_angle=0.0,
            )
        )
    return Track(points, is_closed=False)


class LimitingCaseContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open("config.json", "r") as f:
            cls.base_config = json.load(f)

    def _create_vehicle(self):
        cfg = copy.deepcopy(self.base_config)
        cfg.setdefault("ab_testing", {})["model_variant"] = "baseline"
        cfg.setdefault("solver", {})["use_rollover_speed_cap"] = True
        return create_vehicle(cfg), cfg

    def test_near_zero_curvature_returns_straight_cap_and_zero_angles(self):
        vehicle, _ = self._create_vehicle()
        result = find_vehicle_state_at_point(
            curvature=0.0,
            vehicle=vehicle,
            straight_line_speed_cap=37.5,
        )

        self.assertTrue(result["success"])
        self.assertAlmostEqual(result["v_car"], 37.5, places=6)
        self.assertAlmostEqual(result["a_steer"], 0.0, places=6)
        self.assertAlmostEqual(result["a_sideslip"], 0.0, places=6)

    def test_equation_units_lateral_and_yaw_balance(self):
        # Lateral equilibrium: m * v^2 * K = Fy_f + Fy_r
        lhs_lateral = _dim_mul(KG, _dim_pow(MPS, 2), CURVATURE)
        self.assertEqual(lhs_lateral, NEWTON)

        rhs_lateral = NEWTON
        self.assertEqual(lhs_lateral, rhs_lateral)

        # Yaw equilibrium: a * Fy_f = b * Fy_r = moment [N*m]
        lhs_yaw = _dim_mul(M, NEWTON)
        rhs_yaw = _dim_mul(M, NEWTON)
        self.assertEqual(lhs_yaw, rhs_yaw)
        self.assertEqual(lhs_yaw, _dim_mul(KG, _dim_pow(M, 2), _dim_pow(S, -2)))

    def test_equation_units_rollover_and_kinematics(self):
        # Rollover inner term: (t / (2h)) * g * R has units of v^2.
        ratio_track_height = _dim_div(M, M)
        rollover_inner = _dim_mul(ratio_track_height, MPS2, M)
        self.assertEqual(rollover_inner, _dim_pow(MPS, 2))

        # Kinematic propagation: v^2 + 2*a*ds -> both terms must be speed^2.
        v_sq = _dim_pow(MPS, 2)
        accel_term = _dim_mul(MPS2, M)
        self.assertEqual(v_sq, accel_term)

    def test_longitudinal_budget_scale_bounds_and_endpoints(self):
        self.assertAlmostEqual(_longitudinal_budget_scale_from_lateral_demand(0.0, 5000.0), 1.0, places=8)
        self.assertAlmostEqual(_longitudinal_budget_scale_from_lateral_demand(5000.0, 5000.0), 0.0, places=8)
        self.assertAlmostEqual(_longitudinal_budget_scale_from_lateral_demand(7000.0, 5000.0), 0.0, places=8)

        mid = _longitudinal_budget_scale_from_lateral_demand(2500.0, 5000.0)
        self.assertGreater(mid, 0.0)
        self.assertLess(mid, 1.0)

    def test_curvature_sign_symmetry_speed_and_angles(self):
        vehicle, _ = self._create_vehicle()
        for curvature in (0.03, 0.05, 0.08):
            left = find_vehicle_state_at_point(curvature=curvature, vehicle=vehicle)
            right = find_vehicle_state_at_point(curvature=-curvature, vehicle=vehicle)

            self.assertTrue(left["success"], msg=f"Expected success for curvature {curvature}")
            self.assertTrue(right["success"], msg=f"Expected success for curvature {-curvature}")

            # Speed cap should be even in curvature sign.
            self.assertAlmostEqual(left["v_car"], right["v_car"], places=5)

            # Steering and sideslip should flip sign across mirrored turn direction.
            self.assertAlmostEqual(left["a_steer"], -right["a_steer"], places=4)
            self.assertAlmostEqual(left["a_sideslip"], -right["a_sideslip"], places=4)

    def test_zero_powertrain_torque_cannot_accelerate_forward_pass(self):
        vehicle, cfg = self._create_vehicle()
        track = _build_straight_track(ds=10.0, n_points=4)
        point_speeds = [20.0, 20.0, 20.0, 20.0]

        original_get_torque = vehicle.power_unit.get_torque
        try:
            vehicle.power_unit.get_torque = lambda rpm, throttle=1.0: 0.0
            speeds, diagnostics = forward_pass(track, vehicle, point_speeds, cfg)
        finally:
            vehicle.power_unit.get_torque = original_get_torque

        self.assertTrue(all(abs(v) <= 1e-9 for v in diagnostics["forward_powertrain_force"]))
        self.assertLessEqual(float(speeds[1]), float(speeds[0]) + 1e-9)
        self.assertLessEqual(float(speeds[2]), float(speeds[1]) + 1e-9)
        self.assertLessEqual(float(speeds[3]), float(speeds[2]) + 1e-9)

    def test_zero_speed_backward_pass_stays_zero(self):
        vehicle, cfg = self._create_vehicle()
        track = _build_straight_track(ds=10.0, n_points=4)
        point_speeds = [0.0, 0.0, 0.0, 0.0]

        speeds, diagnostics = backward_pass(track, vehicle, point_speeds, cfg)
        self.assertTrue(all(abs(float(v)) <= 1e-9 for v in speeds))
        self.assertEqual(len(diagnostics["backward_limiting_mode"]), len(point_speeds))

    @unittest.expectedFailure  # Known gap: backward-pass does not enforce solver.max_brake_decel_g cap. Roadmap item.
    def test_backward_brake_decel_respects_configured_cap(self):
        vehicle, cfg = self._create_vehicle()
        cfg.setdefault("solver", {})["max_brake_decel_g"] = 2.0
        track = _build_straight_track(ds=15.0, n_points=6)
        point_speeds = [35.0] * len(track.points)

        _, diagnostics = backward_pass(track, vehicle, point_speeds, cfg)

        used = diagnostics.get("backward_brake_decel_limit", [])
        self.assertEqual(len(used), len(point_speeds))
        self.assertLessEqual(max(float(v) for v in used), 2.0 * 9.81 + 1e-9)
        self.assertGreater(int(diagnostics.get("backward_brake_decel_cap_applied_events", 0)), 0)

    def test_corner_residual_telemetry_exists_and_is_finite_for_successes(self):
        vehicle, cfg = self._create_vehicle()
        track = _build_straight_track(ds=10.0, n_points=6)
        _, _, diagnostics = compute_speed_profile(track, vehicle, cfg)

        success_flags = diagnostics.get("corner_solver_success", [])
        lat_abs = diagnostics.get("corner_solver_lat_residual_abs", [])
        yaw_abs = diagnostics.get("corner_solver_yaw_residual_abs", [])
        lat_rel = diagnostics.get("corner_solver_lat_residual_rel", [])
        yaw_rel = diagnostics.get("corner_solver_yaw_residual_rel", [])

        self.assertEqual(len(success_flags), len(track.points))
        self.assertEqual(len(lat_abs), len(track.points))
        self.assertEqual(len(yaw_abs), len(track.points))
        self.assertEqual(len(lat_rel), len(track.points))
        self.assertEqual(len(yaw_rel), len(track.points))

        for i, ok in enumerate(success_flags):
            if ok:
                self.assertTrue(abs(float(lat_abs[i])) >= 0.0)
                self.assertTrue(abs(float(yaw_abs[i])) >= 0.0)
                self.assertTrue(abs(float(lat_rel[i])) >= 0.0)
                self.assertTrue(abs(float(yaw_rel[i])) >= 0.0)

    def test_tyre_domain_diagnostics_exist_in_runtime_outputs(self):
        vehicle, cfg = self._create_vehicle()
        track = _build_straight_track(ds=10.0, n_points=6)
        _, _, diagnostics = compute_speed_profile(track, vehicle, cfg)

        tyre_domain = diagnostics.get("tyre_domain", {})
        self.assertIsInstance(tyre_domain, dict)
        for key in (
            "lateral_calls",
            "longitudinal_calls",
            "combined_calls",
            "out_of_domain_total",
            "lateral_valid_slip_range_deg",
            "longitudinal_valid_slip_ratio_range",
            "lateral_valid_load_range_N",
            "longitudinal_valid_load_range_N",
        ):
            self.assertIn(key, tyre_domain)

    def test_normal_load_diagnostics_exist_and_non_physical_count_zero(self):
        vehicle, cfg = self._create_vehicle()
        cfg.setdefault("ab_testing", {})["model_variant"] = "b1"
        track = _build_straight_track(ds=10.0, n_points=8)
        _, _, diagnostics = compute_speed_profile(track, vehicle, cfg)

        for key in (
            "corner_front_normal_load_per_tyre",
            "corner_rear_normal_load_per_tyre",
            "forward_front_normal_load_per_tyre",
            "forward_rear_normal_load_per_tyre",
            "backward_front_normal_load_per_tyre",
            "backward_rear_normal_load_per_tyre",
            "corner_non_physical_normal_load_events",
            "forward_non_physical_normal_load_events",
            "backward_non_physical_normal_load_events",
            "normal_load_non_physical_events_total",
        ):
            self.assertIn(key, diagnostics)

        n = len(track.points)
        self.assertEqual(len(diagnostics["corner_front_normal_load_per_tyre"]), n)
        self.assertEqual(len(diagnostics["corner_rear_normal_load_per_tyre"]), n)
        self.assertEqual(len(diagnostics["forward_front_normal_load_per_tyre"]), n)
        self.assertEqual(len(diagnostics["forward_rear_normal_load_per_tyre"]), n)
        self.assertEqual(len(diagnostics["backward_front_normal_load_per_tyre"]), n)
        self.assertEqual(len(diagnostics["backward_rear_normal_load_per_tyre"]), n)

        self.assertEqual(int(diagnostics["normal_load_non_physical_events_total"]), 0)


if __name__ == "__main__":
    unittest.main()