import pytest

from app.paths import resolve_repo_path


def test_resolve_repo_path_accepts_known_relative_path():
    p = resolve_repo_path("datasets/tracks/FSUK.txt")
    assert p.exists()


def test_resolve_repo_path_rejects_absolute_path():
    for hostile in ["/etc/passwd", "C:\\Windows\\System32", "/tmp/x"]:
        with pytest.raises(ValueError):
            resolve_repo_path(hostile)


def test_resolve_repo_path_rejects_parent_traversal():
    for hostile in ["../etc/passwd", "datasets/../../etc/passwd", "..\\windows"]:
        with pytest.raises(ValueError):
            resolve_repo_path(hostile)


def test_resolve_repo_path_rejects_empty():
    with pytest.raises(ValueError):
        resolve_repo_path("")
