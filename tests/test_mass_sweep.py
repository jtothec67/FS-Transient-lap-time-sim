import json
import math
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "tools" / "sweeps" / "mass_sweep.py"


def test_mass_sweep_shape(tmp_path):
    out_file = tmp_path / "sweep.json"

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--min", "250",
            "--max", "260",
            "--step", "5",
            "--out", str(out_file),
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, f"Script exited non-zero.\nstdout: {result.stdout}\nstderr: {result.stderr}"
    assert out_file.exists(), "Output file was not created."

    data = json.loads(out_file.read_text(encoding="utf-8"))

    assert "generated_at" in data
    assert "track" in data
    assert "baseline_mass_kg" in data
    assert "mass_kg" in data
    assert "points" in data

    assert data["mass_kg"]["min"] == 250.0
    assert data["mass_kg"]["max"] == 260.0
    assert data["mass_kg"]["step"] == 5.0

    points = data["points"]
    assert len(points) == 3, f"Expected 3 points, got {len(points)}"

    mass_values = [p["mass_kg"] for p in points]
    assert mass_values == [250.0, 255.0, 260.0], f"Unexpected mass values: {mass_values}"

    numeric_fields = ["lap_time_s", "top_speed_kmh", "max_abs_g_lat", "max_abs_g_long"]
    for point in points:
        for field in numeric_fields:
            assert field in point, f"Missing field {field} in point {point}"
            value = point[field]
            assert isinstance(value, (int, float)), f"Field {field} is not numeric: {value}"
            assert math.isfinite(value), f"Field {field} is not finite: {value}"
