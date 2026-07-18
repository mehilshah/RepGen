"""Tests for local project support."""

from __future__ import annotations

import pytest

from repgen.projects import create_project, open_project
from repgen.projects.local import discover_local_modules


def test_create_plain_project(tmp_path):
    root = tmp_path / "proj"
    project = create_project(str(root), framework="plain")
    assert project.created
    assert (root / "main.py").exists()
    assert (root / "requirements.txt").exists()
    assert project.framework == "plain"


def test_create_fastapi_scaffold(tmp_path):
    project = create_project(str(tmp_path / "api"), framework="fastapi")
    assert (project.path / "app.py").exists()
    assert "fastapi" in (project.path / "requirements.txt").read_text().lower()


def test_create_into_nonempty_without_force_raises(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    (root / "keep.txt").write_text("x")
    with pytest.raises(FileExistsError):
        create_project(str(root), framework="plain")


def test_create_force_into_nonempty(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    (root / "keep.txt").write_text("x")
    project = create_project(str(root), framework="plain", exist_ok=True)
    assert (root / "main.py").exists()
    assert (root / "keep.txt").exists()


def test_open_missing_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        open_project(str(tmp_path / "nope"))


def test_open_detects_framework(tmp_path):
    root = tmp_path / "flaskapp"
    root.mkdir()
    (root / "requirements.txt").write_text("flask\n")
    (root / "app.py").write_text("from flask import Flask\n")
    project = open_project(str(root))
    assert project.framework == "flask"
    assert "app" in project.local_modules


def test_discover_local_modules_ignores_venv(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text("")
    (tmp_path / "mod.py").write_text("x = 1\n")
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv" / "lib.py").write_text("y = 2\n")
    modules = discover_local_modules(tmp_path)
    assert "pkg" in modules
    assert "mod" in modules
    assert ".venv" not in modules
    assert "lib" not in modules


def test_open_detects_django_by_manage_py(tmp_path):
    root = tmp_path / "dj"
    root.mkdir()
    (root / "manage.py").write_text("# django\n")
    assert open_project(str(root)).framework == "django"
