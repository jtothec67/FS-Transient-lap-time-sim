import pytest

from app.security.dataset_registry import (
    get_track_path,
    get_tyre_lateral_path,
    get_tyre_longitudinal_path,
    list_track_ids,
    list_tyre_lateral_ids,
    list_tyre_longitudinal_ids,
)


def test_get_track_path_known_id_returns_existing_file():
    path = get_track_path("FSUK")
    assert path.exists()
    assert path.name == "FSUK.txt"


def test_get_track_path_unknown_id_raises():
    with pytest.raises(ValueError, match="Unknown track id"):
        get_track_path("not_a_real_track")


def test_get_track_path_rejects_traversal_attempts():
    for hostile in ["../etc/passwd", "..\\..\\Windows", "/etc/passwd", "C:\\Windows", ""]:
        with pytest.raises(ValueError):
            get_track_path(hostile)


def test_list_track_ids_includes_seeded_tracks():
    ids = list_track_ids()
    assert "FSUK" in ids
    assert "SkidpadF26" in ids
    assert "StraightLineTrack" in ids


def test_get_tyre_lateral_path_known_id_returns_existing_file():
    path = get_tyre_lateral_path("round_8_12psi")
    assert path.exists()


def test_get_tyre_longitudinal_path_known_id_returns_existing_file():
    path = get_tyre_longitudinal_path("round_6_12psi")
    assert path.exists()


def test_tyre_ids_reject_unknown():
    with pytest.raises(ValueError):
        get_tyre_lateral_path("nope")
    with pytest.raises(ValueError):
        get_tyre_longitudinal_path("nope")


def test_lists_are_non_empty():
    assert list_tyre_lateral_ids()
    assert list_tyre_longitudinal_ids()
