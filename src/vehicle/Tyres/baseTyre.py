import pandas as pd
import numpy as np
import os
import json
from scipy.interpolate import interp1d
from scipy.optimize import least_squares
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
import re


class BaseTyreModel(ABC):
    """
    Abstract base class for tyre models.
    All tyre models should inherit from this class and implement its abstract methods.
    """
    
    def __init__(self):
        """Initialize the base tyre model."""
        pass
    
    @classmethod
    @abstractmethod
    def from_config(cls, config: Dict[str, Any]):
        """
        Create a tyre model from configuration.
        
        Args:
            config: Dictionary containing configuration parameters
            
        Returns:
            An instance of the tyre model
        """
        pass
    
    @abstractmethod
    def get_lateral_force(self, slipAngle: float, normalLoad: Optional[float] = None, 
                        camberAngle: Optional[float] = None, 
                        tyrePressure: Optional[float] = None,
                        temperature: Optional[float] = None) -> float:
        """
        Get lateral force for a given slip angle and conditions.
        
        Args:
            slipAngle: Slip angle in degrees
            normalLoad: Normal load in N (optional)
            camberAngle: Camber angle in degrees (optional)
            tyrePressure: Tyre pressure in kPa (optional)
            temperature: Tyre temperature in °C (optional)
            
        Returns:
            Lateral force in N
        """
        pass
    
    @abstractmethod
    def get_longitudinal_force(self, slipRatio: float, normalLoad: Optional[float] = None,
                            tyrePressure: Optional[float] = None,
                            temperature: Optional[float] = None) -> float:
        """
        Get longitudinal force for a given slip ratio and conditions.
        
        Args:
            slipRatio: Slip ratio (dimensionless)
            normalLoad: Normal load in N (optional)
            tyrePressure: Tyre pressure in kPa (optional)
            temperature: Tyre temperature in °C (optional)
            
        Returns:
            Longitudinal force in N
        """
        pass
    
    @abstractmethod
    def get_combined_forces(self, slipAngle: float, slipRatio: float, 
                         normalLoad: Optional[float] = None) -> tuple:
        """
        Get combined lateral and longitudinal forces when both slip angle and slip ratio exist.
        
        Args:
            slipAngle: Slip angle in degrees
            slipRatio: Slip ratio (dimensionless)
            normalLoad: Normal load in N (optional)
            
        Returns:
            Tuple of (lateral_force, longitudinal_force) in N
        """
        pass


class LookupTableTyreModel(BaseTyreModel):
    """
    Tyre model that uses lookup tables for force calculations with Pacejka magic formula.
    
    Flow:
    1. Parse CSV files via _parse_lateral_file / _parse_longitudinal_file
    2. Build peak force vs normal load interpolators
    3. For a given (slip, normal_load) input:
       - Interpolate peak force D at the given normal load
       - Compute B as a function of D
       - Apply Pacejka formula to get force
    """
    
    # Pacejka shape factors (can be tuned)
    C_LAT = 1.3      # Shape factor for lateral
    C_LONG = 1.65    # Shape factor for longitudinal
    E_LAT = 0.3      # Curvature factor for lateral
    E_LONG = 0.1     # Curvature factor for longitudinal
    B_LAT = 8.6      # Default lateral stiffness factor
    B_LONG = 12.0    # Default longitudinal stiffness factor
    MIN_NORMAL_LOAD_N = 1e-9
    
    def __init__(
        self,
        tyre_data_lat: pd.DataFrame,
        tyre_data_long: pd.DataFrame,
        base_mu: float = 1.0,
        clamp_peak_load_high: bool = True,
        # clamp_peak_load_high=True: peak force interpolation is clamped to the highest measured
        # TTC load rather than extrapolating linearly. Linear extrapolation above the measured
        # range is unphysical (tyre load sensitivity inverts at high load). Default is True.
    ):
        """
        Initialize lookup table tyre model.
        
        Args:
            tyre_data_lat: DataFrame with lateral tyre data
            tyre_data_long: DataFrame with longitudinal tyre data
        """
        super().__init__()
        self.tyre_data_lat = tyre_data_lat
        self.tyre_data_long = tyre_data_long
        self.base_mu = float(base_mu)
        self.clamp_peak_load_high = bool(clamp_peak_load_high)
        self._longitudinal_slip_data_is_ratio = True
        self._lat_shape = (self.B_LAT, self.C_LAT, self.E_LAT)
        self._long_shape = (self.B_LONG, self.C_LONG, self.E_LONG)
        self._lat_slip_min_deg = np.nan
        self._lat_slip_max_deg = np.nan
        self._long_slip_min_ratio = np.nan
        self._long_slip_max_ratio = np.nan
        self._lat_load_min_N = np.nan
        self._lat_load_max_N = np.nan
        self._long_load_min_N = np.nan
        self._long_load_max_N = np.nan
        self._lat_mu_reference = 1.0
        self._long_mu_reference = 1.0
        self._domain_diag = {
            "lateral_calls": 0,
            "longitudinal_calls": 0,
            "combined_calls": 0,
            "lateral_out_of_domain_slip": 0,
            "lateral_out_of_domain_load": 0,
            "longitudinal_out_of_domain_slip": 0,
            "longitudinal_out_of_domain_load": 0,
            "combined_out_of_domain_any": 0,
            "clamped_high_load_lateral": 0,
            "clamped_high_load_longitudinal": 0,
        }

        # Build peak-vs-load interpolators (used by Pacejka D = peak)
        self._build_peak_interps()
        self._detect_longitudinal_slip_units()
        self._initialize_validity_domains()
        self._fit_magic_formula_shapes()

    def reset_domain_diagnostics(self):
        for key in self._domain_diag:
            self._domain_diag[key] = 0

    def get_domain_diagnostics(self) -> Dict[str, float]:
        diag = dict(self._domain_diag)
        diag["lateral_valid_slip_range_deg"] = [
            None if not np.isfinite(self._lat_slip_min_deg) else float(self._lat_slip_min_deg),
            None if not np.isfinite(self._lat_slip_max_deg) else float(self._lat_slip_max_deg),
        ]
        diag["longitudinal_valid_slip_ratio_range"] = [
            None if not np.isfinite(self._long_slip_min_ratio) else float(self._long_slip_min_ratio),
            None if not np.isfinite(self._long_slip_max_ratio) else float(self._long_slip_max_ratio),
        ]
        diag["lateral_valid_load_range_N"] = [
            None if not np.isfinite(self._lat_load_min_N) else float(self._lat_load_min_N),
            None if not np.isfinite(self._lat_load_max_N) else float(self._lat_load_max_N),
        ]
        diag["longitudinal_valid_load_range_N"] = [
            None if not np.isfinite(self._long_load_min_N) else float(self._long_load_min_N),
            None if not np.isfinite(self._long_load_max_N) else float(self._long_load_max_N),
        ]
        diag["lateral_peak_mu_reference"] = float(self._lat_mu_reference)
        diag["longitudinal_peak_mu_reference"] = float(self._long_mu_reference)
        diag["lateral_base_mu_scale"] = float(self._base_mu_scale_lateral())
        diag["longitudinal_base_mu_scale"] = float(self._base_mu_scale_longitudinal())
        diag["out_of_domain_total"] = int(
            diag["lateral_out_of_domain_slip"]
            + diag["lateral_out_of_domain_load"]
            + diag["longitudinal_out_of_domain_slip"]
            + diag["longitudinal_out_of_domain_load"]
            + diag["combined_out_of_domain_any"]
        )
        return diag

    def _initialize_validity_domains(self):
        lat = self.tyre_data_lat.dropna(subset=["Slip Angle [deg]"])
        if not lat.empty:
            lat_slip = pd.to_numeric(lat["Slip Angle [deg]"], errors="coerce").dropna().to_numpy(dtype=float)
            if len(lat_slip):
                self._lat_slip_min_deg = float(np.min(lat_slip))
                self._lat_slip_max_deg = float(np.max(lat_slip))

        if hasattr(self, "_lat_loads") and len(self._lat_loads):
            self._lat_load_min_N = float(np.min(self._lat_loads))
            self._lat_load_max_N = float(np.max(self._lat_loads))

        lon = self.tyre_data_long.dropna(subset=["Slip Ratio [%]"])
        if not lon.empty:
            lon_slip_raw = pd.to_numeric(lon["Slip Ratio [%]"], errors="coerce").dropna().to_numpy(dtype=float)
            if len(lon_slip_raw):
                if self._longitudinal_slip_data_is_ratio:
                    lon_kappa = lon_slip_raw
                else:
                    lon_kappa = lon_slip_raw / 100.0
                self._long_slip_min_ratio = float(np.min(lon_kappa))
                self._long_slip_max_ratio = float(np.max(lon_kappa))

        if hasattr(self, "_long_loads") and len(self._long_loads):
            self._long_load_min_N = float(np.min(self._long_loads))
            self._long_load_max_N = float(np.max(self._long_loads))

    @staticmethod
    def _outside_range(value: float, lo: float, hi: float) -> bool:
        if not np.isfinite(value):
            return False
        if not np.isfinite(lo) or not np.isfinite(hi):
            return False
        return (value < lo) or (value > hi)

    def _detect_longitudinal_slip_units(self):
        """
        Detect longitudinal slip units in the parsed dataset.
        Heuristic: if max(|slip|) <= 2, data is likely dimensionless ratio.
        """
        try:
            s = pd.to_numeric(self.tyre_data_long.get('Slip Ratio [%]'), errors='coerce').dropna()
            if s.empty:
                self._longitudinal_slip_data_is_ratio = True
                return
            self._longitudinal_slip_data_is_ratio = float(s.abs().max()) <= 2.0
        except Exception:
            self._longitudinal_slip_data_is_ratio = True

    @staticmethod
    def _mf_unit_curve(slip: np.ndarray, B: float, C: float, E: float) -> np.ndarray:
        """Unit-amplitude Magic Formula curve."""
        bx = B * slip
        return np.sin(C * np.arctan(bx - E * (bx - np.arctan(bx))))

    def _fit_shape_params(self, slips: np.ndarray, forces: np.ndarray, loads: np.ndarray, peak_interp, defaults):
        """
        Fit global (B, C, E) for a pure-slip MF curve with load-dependent D(load).
        """
        try:
            d_vals = np.asarray(peak_interp(loads), dtype=float)
            d_vals = np.maximum(np.abs(d_vals), 1e-6)
            y = np.asarray(forces, dtype=float) / d_vals

            valid = np.isfinite(slips) & np.isfinite(y)
            x = slips[valid]
            y = y[valid]
            if x.size < 50:
                return defaults

            # Keep optimizer robust to noisy tails.
            y = np.clip(y, -1.5, 1.5)

            def residuals(p):
                b, c, e = p
                return self._mf_unit_curve(x, b, c, e) - y

            p0 = np.asarray(defaults, dtype=float)
            lb = np.array([0.1, 0.5, -2.0], dtype=float)
            ub = np.array([40.0, 3.0, 2.0], dtype=float)
            res = least_squares(residuals, p0, bounds=(lb, ub), max_nfev=2000)
            if not res.success:
                return defaults
            fitted = tuple(float(v) for v in res.x)
            if any(not np.isfinite(v) for v in fitted):
                return defaults
            return fitted
        except Exception:
            return defaults

    def _fit_magic_formula_shapes(self):
        """Fit MF shape parameters against parsed lateral/longitudinal TTC-derived data."""
        # Lateral fit
        lat = self.tyre_data_lat.dropna(subset=['Slip Angle [deg]', 'Lateral Force [N]', 'Normal Load [N]'])
        if (not lat.empty) and (self._lat_peak_interp is not None):
            lat_slip = np.radians(pd.to_numeric(lat['Slip Angle [deg]'], errors='coerce').to_numpy(dtype=float))
            lat_force = pd.to_numeric(lat['Lateral Force [N]'], errors='coerce').to_numpy(dtype=float)
            lat_load = pd.to_numeric(lat['Normal Load [N]'], errors='coerce').to_numpy(dtype=float)
            self._lat_shape = self._fit_shape_params(
                slips=lat_slip,
                forces=lat_force,
                loads=lat_load,
                peak_interp=self._lat_peak_interp,
                defaults=self._lat_shape,
            )

        # Longitudinal fit
        lon = self.tyre_data_long.dropna(subset=['Slip Ratio [%]', 'Longitudinal Force [N]', 'Normal Load [N]'])
        if (not lon.empty) and (self._long_peak_interp is not None):
            raw_slip = pd.to_numeric(lon['Slip Ratio [%]'], errors='coerce').to_numpy(dtype=float)
            if self._longitudinal_slip_data_is_ratio:
                lon_slip = raw_slip
            else:
                lon_slip = raw_slip / 100.0

            lon_force = pd.to_numeric(lon['Longitudinal Force [N]'], errors='coerce').to_numpy(dtype=float)
            lon_load = pd.to_numeric(lon['Normal Load [N]'], errors='coerce').to_numpy(dtype=float)
            self._long_shape = self._fit_shape_params(
                slips=lon_slip,
                forces=lon_force,
                loads=lon_load,
                peak_interp=self._long_peak_interp,
                defaults=self._long_shape,
            )

    def _build_peak_interps(self):
        """Build peak force vs normal-load interpolators for lateral and longitudinal."""
        import logging
        logger = logging.getLogger(__name__)

        # Ensure numeric columns for lateral
        if 'Normal Load [N]' in self.tyre_data_lat.columns:
            self.tyre_data_lat['Normal Load [N]'] = pd.to_numeric(self.tyre_data_lat['Normal Load [N]'], errors='coerce')
        if 'Lateral Force [N]' in self.tyre_data_lat.columns:
            self.tyre_data_lat['Lateral Force [N]'] = pd.to_numeric(self.tyre_data_lat['Lateral Force [N]'], errors='coerce')

        # Lateral peaks: group by normal load, find max absolute force
        lat = self.tyre_data_lat.dropna(subset=['Normal Load [N]', 'Lateral Force [N]'])
        if not lat.empty:
            grp = lat.groupby('Normal Load [N]')['Lateral Force [N]'].agg(lambda s: float(np.nanmax(np.abs(s.values)))).reset_index()
            grp = grp.sort_values('Normal Load [N]').reset_index(drop=True)
            self._lat_loads = grp['Normal Load [N]'].to_numpy(dtype=float)
            self._lat_peaks = grp['Lateral Force [N]'].to_numpy(dtype=float)
            logger.debug("Lateral peak loads: %s", self._lat_loads)
            logger.debug("Lateral peak values: %s", self._lat_peaks)
            if len(self._lat_loads) >= 2:
                self._lat_peak_interp = interp1d(self._lat_loads, self._lat_peaks, kind='linear', fill_value='extrapolate', assume_sorted=True)
            elif len(self._lat_loads) == 1:
                const = float(self._lat_peaks[0])
                self._lat_peak_interp = lambda x, c=const: np.full_like(np.atleast_1d(x), c, dtype=float)
            else:
                self._lat_peak_interp = None
        else:
            self._lat_loads = np.array([])
            self._lat_peaks = np.array([])
            self._lat_peak_interp = None

        self._lat_mu_reference = self._infer_peak_mu_reference(self._lat_loads, self._lat_peaks)

        # Ensure numeric columns for longitudinal
        if 'Normal Load [N]' in self.tyre_data_long.columns:
            self.tyre_data_long['Normal Load [N]'] = pd.to_numeric(self.tyre_data_long['Normal Load [N]'], errors='coerce')
        if 'Longitudinal Force [N]' in self.tyre_data_long.columns:
            self.tyre_data_long['Longitudinal Force [N]'] = pd.to_numeric(self.tyre_data_long['Longitudinal Force [N]'], errors='coerce')

        # Longitudinal peaks: group by normal load, find max absolute force
        lon = self.tyre_data_long.dropna(subset=['Normal Load [N]', 'Longitudinal Force [N]'])
        if not lon.empty:
            grp = lon.groupby('Normal Load [N]')['Longitudinal Force [N]'].agg(lambda s: float(np.nanmax(np.abs(s.values)))).reset_index()
            grp = grp.sort_values('Normal Load [N]').reset_index(drop=True)
            self._long_loads = grp['Normal Load [N]'].to_numpy(dtype=float)
            self._long_peaks = grp['Longitudinal Force [N]'].to_numpy(dtype=float)
            logger.debug("Longitudinal peak loads: %s", self._long_loads)
            logger.debug("Longitudinal peak values: %s", self._long_peaks)
            if len(self._long_loads) >= 2:
                self._long_peak_interp = interp1d(self._long_loads, self._long_peaks, kind='linear', fill_value='extrapolate', assume_sorted=True)
            elif len(self._long_loads) == 1:
                const = float(self._long_peaks[0])
                self._long_peak_interp = lambda x, c=const: np.full_like(np.atleast_1d(x), c, dtype=float)
            else:
                self._long_peak_interp = None
        else:
            self._long_loads = np.array([])
            self._long_peaks = np.array([])
            self._long_peak_interp = None

        self._long_mu_reference = self._infer_peak_mu_reference(self._long_loads, self._long_peaks)

    @staticmethod
    def _infer_peak_mu_reference(loads: np.ndarray, peaks: np.ndarray) -> float:
        """
        Infer a reference friction level from measured peak force/load pairs.

        TTC peak tables in this model are absolute force values, so we normalize
        them to a representative peak force ratio before applying base_mu.
        """
        try:
            loads_arr = np.asarray(loads, dtype=float)
            peaks_arr = np.asarray(peaks, dtype=float)
        except Exception:
            return 1.0

        if loads_arr.size == 0 or peaks_arr.size == 0:
            return 1.0

        valid = np.isfinite(loads_arr) & np.isfinite(peaks_arr) & (loads_arr > 1e-9)
        if not np.any(valid):
            return 1.0

        mu_vals = np.abs(peaks_arr[valid]) / loads_arr[valid]
        mu_vals = mu_vals[np.isfinite(mu_vals) & (mu_vals > 1e-9)]
        if mu_vals.size == 0:
            return 1.0

        return max(float(np.median(mu_vals)), 1e-6)

    def _base_mu_scale_lateral(self) -> float:
        return float(self.base_mu) / max(float(self._lat_mu_reference), 1e-6)

    def _base_mu_scale_longitudinal(self) -> float:
        return float(self.base_mu) / max(float(self._long_mu_reference), 1e-6)

    def _compute_B_lateral(self, D: float) -> float:
        """
        Compute B (stiffness factor) for lateral force as a function of peak force D.
        B controls how quickly the curve rises. Higher B = steeper initial slope.
        """
        if D <= 0:
            return self.B_LAT
        return float(self._lat_shape[0])

    def _compute_B_longitudinal(self, D: float) -> float:
        """
        Compute B (stiffness factor) for longitudinal force as a function of peak force D.
        """
        if D <= 0:
            return self.B_LONG
        return float(self._long_shape[0])

    def _coerce_slip_ratio_to_kappa(self, slip_ratio: float) -> float:
        """
        Convert caller input to dimensionless slip ratio kappa.
        - If |slip_ratio| > 2, interpret as percent (legacy behavior).
        - Otherwise, interpret as already dimensionless ratio.
        """
        sr = float(slip_ratio)
        if abs(sr) > 2.0:
            return sr / 100.0
        return sr

    def _resolve_peak_load_input(self, normal_load: float, channel: str) -> float:
        """
        Resolve effective normal load used for peak interpolation.

        Baseline behavior keeps linear extrapolation. Variant behavior can clamp
        high-load extrapolation to the highest measured TTC load.
        """
        load = float(normal_load)
        if not self.clamp_peak_load_high:
            return load

        if channel == 'lateral':
            loads = getattr(self, '_lat_loads', np.array([]))
        else:
            loads = getattr(self, '_long_loads', np.array([]))

        if loads is None or len(loads) == 0:
            return load

        max_load = float(np.nanmax(loads))
        if np.isfinite(max_load):
            if load > max_load:
                if channel == 'lateral':
                    self._domain_diag["clamped_high_load_lateral"] += 1
                else:
                    self._domain_diag["clamped_high_load_longitudinal"] += 1
            return min(load, max_load)
        return load

    def _pacejka(self, slip: float, D: float, C: float, B: float, E: float) -> float:
        """
        Pacejka Magic Formula: F = D * sin(C * arctan(B*slip - E*(B*slip - arctan(B*slip))))
        
        Args:
            slip: Slip value (radians for lateral, dimensionless ratio for longitudinal)
            D: Peak force
            C: Shape factor
            B: Stiffness factor
            E: Curvature factor
        
        Returns:
            Force in N
        """
        Bx = B * slip
        return D * np.sin(C * np.arctan(Bx - E * (Bx - np.arctan(Bx))))

    def _is_zero_or_negative_load(self, normal_load: float) -> bool:
        return float(normal_load) <= self.MIN_NORMAL_LOAD_N

    def get_lateral_force(self, slip_angle: float, normal_load: Optional[float] = None, 
                        camber_angle: Optional[float] = None, 
                        tyre_pressure: Optional[float] = None,
                        temperature: Optional[float] = None) -> float:
        """
        Get lateral force for given slip angle and normal load.
        
        Args:
            slip_angle: Slip angle in degrees
            normal_load: Normal load in N (required for proper force calculation)
        
        Returns:
            Lateral force in N
        """
        if normal_load is None or self._lat_peak_interp is None:
            raise ValueError("Normal load is required and lateral peak interpolator must be available")

        self._domain_diag["lateral_calls"] += 1
        slip_deg = float(slip_angle)
        load_val = float(normal_load)
        if self._outside_range(slip_deg, self._lat_slip_min_deg, self._lat_slip_max_deg):
            self._domain_diag["lateral_out_of_domain_slip"] += 1
        if self._outside_range(load_val, self._lat_load_min_N, self._lat_load_max_N):
            self._domain_diag["lateral_out_of_domain_load"] += 1

        if self._is_zero_or_negative_load(normal_load):
            return 0.0
        
        # Get peak force D by interpolating at the given normal load
        interp_load = self._resolve_peak_load_input(normal_load, 'lateral')
        D = max(0.0, float(self._lat_peak_interp(interp_load)) * self._base_mu_scale_lateral())
        
        # Compute B as function of D
        B = self._compute_B_lateral(D)
        
        # Convert slip angle to radians
        alpha = np.radians(slip_deg)
        
        # Apply Pacejka formula
        c_lat = float(self._lat_shape[1])
        e_lat = float(self._lat_shape[2])
        fy = self._pacejka(alpha, D, c_lat, B, e_lat)
        return float(fy)

    def get_longitudinal_force(self, slip_ratio: float, normal_load: Optional[float] = None,
                              tyre_pressure: Optional[float] = None,
                              temperature: Optional[float] = None) -> float:
        """
        Get longitudinal force for given slip ratio and normal load.
        
        Args:
            slip_ratio: Slip ratio in percent (0-100 range expected from data)
            normal_load: Normal load in N (required for proper force calculation)
        
        Returns:
            Longitudinal force in N
        """
        if normal_load is None or self._long_peak_interp is None:
            raise ValueError("Normal load is required and longitudinal peak interpolator must be available")

        self._domain_diag["longitudinal_calls"] += 1
        load_val = float(normal_load)

        if self._is_zero_or_negative_load(normal_load):
            return 0.0
        
        # Get peak force D by interpolating at the given normal load
        interp_load = self._resolve_peak_load_input(normal_load, 'longitudinal')
        D = max(0.0, float(self._long_peak_interp(interp_load)) * self._base_mu_scale_longitudinal())
        
        # Compute B as function of D
        B = self._compute_B_longitudinal(D)

        # Convert caller input to dimensionless slip ratio (supports percent and ratio inputs)
        kappa = self._coerce_slip_ratio_to_kappa(slip_ratio)
        if self._outside_range(kappa, self._long_slip_min_ratio, self._long_slip_max_ratio):
            self._domain_diag["longitudinal_out_of_domain_slip"] += 1
        if self._outside_range(load_val, self._long_load_min_N, self._long_load_max_N):
            self._domain_diag["longitudinal_out_of_domain_load"] += 1
        
        # Apply Pacejka formula
        c_long = float(self._long_shape[1])
        e_long = float(self._long_shape[2])
        fx = self._pacejka(kappa, D, c_long, B, e_long)
        return float(fx)
    
    @classmethod
    def from_config(cls, config: Dict[str, Any]):
        """
        Create a lookup table tyre model from configuration.
        
        Args:
            config: Dictionary containing configuration parameters with file_path to tyre data
            
        Returns:
            An instance of LookupTableTyreModel
        """
        # Prefer separate lateral/longitudinal file paths if provided
        file_path_longit = config.get('file_path_longit')
        file_path_lateral = config.get('file_path_lateral')

        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))

        try:
            # If both separate paths are provided, parse them individually
            if file_path_longit or file_path_lateral:
                tyre_data_lat = pd.DataFrame(columns=['Slip Angle [deg]', 'Lateral Force [N]', 'Normal Load [N]', 'Camber Angle [deg]', 'Tyre Pressure [kPa]', 'Temperature [C]'])
                tyre_data_long = pd.DataFrame(columns=['Slip Ratio [%]', 'Longitudinal Force [N]', 'Normal Load [N]', 'Tyre Pressure [kPa]', 'Temperature [C]'])

                if file_path_lateral:
                    full_lat = os.path.join(project_root, file_path_lateral)
                    if not os.path.exists(full_lat):
                        raise FileNotFoundError(f"Lateral tyre data file not found: {full_lat}")
                    tyre_data_lat = cls._parse_lateral_file(full_lat)

                if file_path_longit:
                    full_long = os.path.join(project_root, file_path_longit)
                    if not os.path.exists(full_long):
                        raise FileNotFoundError(f"Longitudinal tyre data file not found: {full_long}")
                    tyre_data_long = cls._parse_longitudinal_file(full_long)

                model_variant = str(config.get('model_variant', '')).strip().lower()
                # Default True: extrapolating peak force above measured TTC loads is unphysical.
                clamp_peak_load_high = bool(config.get('clamp_peak_load_high', True))
                if model_variant in {'b2', 'tyre_peak_load_clamp', 'tyre_load_clamp'}:
                    clamp_peak_load_high = True

                return cls(
                    tyre_data_lat,
                    tyre_data_long,
                    base_mu=config.get('base_mu', 1.0),
                    clamp_peak_load_high=clamp_peak_load_high,
                )

        except Exception as e:
            import logging
            logging.error(f"Failed to load tyre data from separate paths: {str(e)}")
            raise

        # Legacy single file path handling (for backward compatibility)
        file_path = config.get('file_path')
        if not file_path:
            raise ValueError("Tyre model config must specify file_path or file_path_longit/file_path_lateral")

        # Get absolute path relative to project root
        full_path = os.path.join(project_root, file_path)

        # Read and process the tyre data file
        # This assumes a specific CSV format - adapt as needed for your data format
        try:
            # Check if file exists
            if not os.path.exists(full_path):
                raise FileNotFoundError(f"Tyre data file not found: {full_path}")

            if file_path.endswith('.csv'):
                # Try to parse as longitudinal grouped CSV first
                tyre_data_long = cls._parse_longitudinal_file(full_path)
                # create empty lateral frame (caller may load lateral separately)
                tyre_data_lat = pd.DataFrame(columns=['Slip Angle [deg]', 'Lateral Force [N]', 'Normal Load [N]', 'Camber Angle [deg]', 'Tyre Pressure [kPa]', 'Temperature [C]'])
            elif file_path.endswith('.json'):
                # For JSON format
                with open(full_path, 'r') as f:
                    tyre_data = json.load(f)
                
                # Extract data based on JSON structure
                lateral_data = tyre_data.get('lateral', {})
                longitudinal_data = tyre_data.get('longitudinal', {})
                
                # Create dataframes
                tyre_data_lat = pd.DataFrame({
                    'Slip Angle [deg]': lateral_data.get('slip_angles', []),
                    'Lateral Force [N]': lateral_data.get('forces', []),
                    'Normal Load [N]': lateral_data.get('normal_loads', [3000] * len(lateral_data.get('slip_angles', []))),
                    'Camber Angle [deg]': lateral_data.get('camber_angles', [0] * len(lateral_data.get('slip_angles', []))),
                    'Tyre Pressure [kPa]': lateral_data.get('pressures', [200] * len(lateral_data.get('slip_angles', []))),
                    'Temperature [C]': lateral_data.get('temperatures', [25] * len(lateral_data.get('slip_angles', [])))
                })
                
                tyre_data_long = pd.DataFrame({
                    'Slip Ratio [%]': longitudinal_data.get('slip_ratios', []),
                    'Longitudinal Force [N]': longitudinal_data.get('forces', []),
                    'Normal Load [N]': longitudinal_data.get('normal_loads', [3000] * len(longitudinal_data.get('slip_ratios', []))),
                    'Tyre Pressure [kPa]': longitudinal_data.get('pressures', [200] * len(longitudinal_data.get('slip_ratios', []))),
                    'Temperature [C]': longitudinal_data.get('temperatures', [25] * len(longitudinal_data.get('slip_ratios', [])))
                })
            else:
                raise ValueError(f"Unsupported file format: {file_path}")
                
            # Return the model
            model_variant = str(config.get('model_variant', '')).strip().lower()
            # Default True: extrapolating peak force above measured TTC loads is unphysical.
            clamp_peak_load_high = bool(config.get('clamp_peak_load_high', True))
            if model_variant in {'b2', 'tyre_peak_load_clamp', 'tyre_load_clamp'}:
                clamp_peak_load_high = True

            return cls(
                tyre_data_lat,
                tyre_data_long,
                base_mu=config.get('base_mu', 1.0),
                clamp_peak_load_high=clamp_peak_load_high,
            )
            
        except Exception as e:
            import logging
            logging.error(f"Failed to load tyre data from {file_path}: {str(e)}")
            raise
    
    def get_combined_forces(self, slip_angle: float, slip_ratio: float, 
                           normal_load: Optional[float] = None) -> tuple:
        """
        Get combined lateral and longitudinal forces using friction circle scaling.
        
        Args:
            slip_angle: Slip angle in degrees
            slip_ratio: Slip ratio in percent
            normal_load: Normal load in N (required)
        
        Returns:
            Tuple of (lateral_force, longitudinal_force) in N
        """
        if normal_load is None:
            raise ValueError("Normal load is required for combined forces calculation")

        self._domain_diag["combined_calls"] += 1
        combined_out = False
        if self._outside_range(float(slip_angle), self._lat_slip_min_deg, self._lat_slip_max_deg):
            combined_out = True
        if self._outside_range(float(self._coerce_slip_ratio_to_kappa(slip_ratio)), self._long_slip_min_ratio, self._long_slip_max_ratio):
            combined_out = True
        if self._outside_range(float(normal_load), self._lat_load_min_N, self._lat_load_max_N) or self._outside_range(float(normal_load), self._long_load_min_N, self._long_load_max_N):
            combined_out = True
        if combined_out:
            self._domain_diag["combined_out_of_domain_any"] += 1

        if self._is_zero_or_negative_load(normal_load):
            return (0.0, 0.0)
        
        # Get pure forces
        fy_pure = self.get_lateral_force(slip_angle, normal_load)
        fx_pure = self.get_longitudinal_force(slip_ratio, normal_load)
        
        # Get peak forces for friction circle limit
        lat_interp_load = self._resolve_peak_load_input(normal_load, 'lateral')
        long_interp_load = self._resolve_peak_load_input(normal_load, 'longitudinal')
        D_lat = max(0.0, (float(self._lat_peak_interp(lat_interp_load)) * self._base_mu_scale_lateral())) if self._lat_peak_interp else abs(fy_pure)
        D_long = max(0.0, (float(self._long_peak_interp(long_interp_load)) * self._base_mu_scale_longitudinal())) if self._long_peak_interp else abs(fx_pure)
        
        # Combined force magnitude
        total_force = np.sqrt(fx_pure**2 + fy_pure**2)
        
        if total_force == 0:
            return (0.0, 0.0)
        
        # Friction ellipse limit (approximate)
        max_combined = np.sqrt(D_lat**2 + D_long**2) * 0.9  # 90% of theoretical max
        
        if total_force > max_combined:
            scale = max_combined / total_force
            fx = fx_pure * scale
            fy = fy_pure * scale
        else:
            fx = fx_pure
            fy = fy_pure
        
        return (float(fy), float(fx))


    @staticmethod
    def _extract_number_from_label(s: str) -> Optional[float]:
        if s is None:
            return None
        s = str(s)
        m = re.search(r'([0-9]+(?:\.[0-9]+)?)', s)
        if not m:
            return None
        try:
            return float(m.group(1))
        except Exception:
            return None

    @staticmethod
    def _parse_longitudinal_file(full_path: str) -> pd.DataFrame:
        """
        Return DataFrame with columns:
         'Slip Ratio [%]', 'Longitudinal Force [N]', 'Normal Load [N]', 'Tyre Pressure [kPa]', 'Temperature [C]'
        Accepts already-parsed CSV (preferred) or grouped SR,Fx,,SR,Fx,,... raw format.
        """
        # try normal parsed CSV first
        try:
            df = pd.read_csv(full_path)
            if {'Slip Ratio [%]', 'Longitudinal Force [N]'} <= set(df.columns):
                df = df.copy()
                df['Slip Ratio [%]'] = pd.to_numeric(df['Slip Ratio [%]'], errors='coerce')
                df['Longitudinal Force [N]'] = pd.to_numeric(df['Longitudinal Force [N]'], errors='coerce')
                if 'Normal Load [N]' not in df.columns:
                    df['Normal Load [N]'] = np.nan
                if 'Tyre Pressure [kPa]' not in df.columns:
                    df['Tyre Pressure [kPa]'] = 200
                if 'Temperature [C]' not in df.columns:
                    df['Temperature [C]'] = 25
                return df[['Slip Ratio [%]', 'Longitudinal Force [N]', 'Normal Load [N]', 'Tyre Pressure [kPa]', 'Temperature [C]']]
        except Exception:
            pass

        # fallback: grouped raw CSV
        raw = pd.read_csv(full_path, header=None, dtype=str)
        if raw.shape[0] < 3:
            # empty/invalid format -> return empty frame with correct columns
            return pd.DataFrame(columns=['Slip Ratio [%]', 'Longitudinal Force [N]', 'Normal Load [N]', 'Tyre Pressure [kPa]', 'Temperature [C]'])
        load_row = raw.iloc[0].fillna('').astype(str).values
        header_row = raw.iloc[1].fillna('').astype(str).values
        data = raw.iloc[2:].reset_index(drop=True).replace('', np.nan)

        groups = []
        ncols = header_row.shape[0]
        col = 0
        while col < ncols - 1:
            h = header_row[col].strip().upper()
            h_next = header_row[col+1].strip().upper() if col+1 < ncols else ''
            if ('SR' in h or 'SLIP' in h) and ('FX' in h_next or 'F' in h_next):
                # extract normal load from same column index in load_row if present
                nl = LookupTableTyreModel._extract_number_from_label(load_row[col])
                slip_series = pd.to_numeric(data.iloc[:, col], errors='coerce')
                force_series = pd.to_numeric(data.iloc[:, col+1], errors='coerce')
                dfg = pd.DataFrame({
                    'Slip Ratio [%]': slip_series,
                    'Longitudinal Force [N]': force_series
                }).dropna(how='any')
                if dfg.empty:
                    col += 3
                    continue
                n = nl if nl is not None else np.nan
                dfg['Normal Load [N]'] = float(n) if not np.isnan(n) else np.nan
                dfg['Tyre Pressure [kPa]'] = 200
                dfg['Temperature [C]'] = 25
                groups.append(dfg[['Slip Ratio [%]', 'Longitudinal Force [N]', 'Normal Load [N]', 'Tyre Pressure [kPa]', 'Temperature [C]']])
                col += 3
                continue
            col += 1

        if groups:
            return pd.concat(groups, ignore_index=True)
        return pd.DataFrame(columns=['Slip Ratio [%]', 'Longitudinal Force [N]', 'Normal Load [N]', 'Tyre Pressure [kPa]', 'Temperature [C]'])

    @staticmethod
    def _parse_lateral_file(full_path: str) -> pd.DataFrame:
        """
        Return DataFrame with columns:
         'Slip Angle [deg]', 'Lateral Force [N]', 'Normal Load [N]', 'Camber Angle [deg]', 'Tyre Pressure [kPa]', 'Temperature [C]'
        Accepts already-parsed CSV (preferred) or grouped SA,Fy,,SA,Fy,,... raw format.
        """
        # try normal parsed CSV first
        try:
            df = pd.read_csv(full_path)
            if {'Slip Angle [deg]', 'Lateral Force [N]'} <= set(df.columns):
                df = df.copy()
                df['Slip Angle [deg]'] = pd.to_numeric(df['Slip Angle [deg]'], errors='coerce')
                df['Lateral Force [N]'] = pd.to_numeric(df['Lateral Force [N]'], errors='coerce')
                if 'Normal Load [N]' not in df.columns:
                    df['Normal Load [N]'] = np.nan
                if 'Camber Angle [deg]' not in df.columns:
                    df['Camber Angle [deg]'] = 0.0
                if 'Tyre Pressure [kPa]' not in df.columns:
                    df['Tyre Pressure [kPa]'] = 200
                if 'Temperature [C]' not in df.columns:
                    df['Temperature [C]'] = 25
                return df[['Slip Angle [deg]', 'Lateral Force [N]', 'Normal Load [N]', 'Camber Angle [deg]', 'Tyre Pressure [kPa]', 'Temperature [C]']]
        except Exception:
            pass

        # fallback: grouped raw CSV
        raw = pd.read_csv(full_path, header=None, dtype=str)
        if raw.shape[0] < 3:
            return pd.DataFrame(columns=['Slip Angle [deg]', 'Lateral Force [N]', 'Normal Load [N]', 'Camber Angle [deg]', 'Tyre Pressure [kPa]', 'Temperature [C]'])
        load_row = raw.iloc[0].fillna('').astype(str).values
        header_row = raw.iloc[1].fillna('').astype(str).values
        data = raw.iloc[2:].reset_index(drop=True).replace('', np.nan)

        groups = []
        ncols = header_row.shape[0]
        col = 0
        while col < ncols - 1:
            h = header_row[col].strip().upper()
            h_next = header_row[col+1].strip().upper() if col+1 < ncols else ''
            if ('SA' in h or 'SLIP' in h or 'S A' in h) and ('FY' in h_next or 'F' in h_next):
                nl = LookupTableTyreModel._extract_number_from_label(load_row[col])
                slip_series = pd.to_numeric(data.iloc[:, col], errors='coerce')
                force_series = pd.to_numeric(data.iloc[:, col+1], errors='coerce')
                dfg = pd.DataFrame({
                    'Slip Angle [deg]': slip_series,
                    'Lateral Force [N]': force_series
                }).dropna(how='any')
                if dfg.empty:
                    col += 3
                    continue
                n = nl if nl is not None else np.nan
                dfg['Normal Load [N]'] = float(n) if not np.isnan(n) else np.nan
                dfg['Camber Angle [deg]'] = 0.0
                dfg['Tyre Pressure [kPa]'] = 200
                dfg['Temperature [C]'] = 25
                groups.append(dfg[['Slip Angle [deg]', 'Lateral Force [N]', 'Normal Load [N]', 'Camber Angle [deg]', 'Tyre Pressure [kPa]', 'Temperature [C]']])
                col += 3
                continue
            col += 1

        if groups:
            return pd.concat(groups, ignore_index=True)
        return pd.DataFrame(columns=['Slip Angle [deg]', 'Lateral Force [N]', 'Normal Load [N]', 'Camber Angle [deg]', 'Tyre Pressure [kPa]', 'Temperature [C]'])
    
def create_tyre_model(config: Dict[str, Any]) -> BaseTyreModel:
    """
    Factory function to create a tyre model based on configuration.
    
    Args:
        config: Dictionary containing configuration parameters with 'type' key
        
    Returns:
        An instance of a tyre model
    """
    tyre_model_type = config.get('type', 'lookup').lower()
    if tyre_model_type == 'lookup':
        return LookupTableTyreModel.from_config(config)
    else:
        raise ValueError(f"Unsupported tyre model type: {tyre_model_type}")
