"""Tests for the dependency resolver and requirements.txt management."""

from __future__ import annotations

from repgen.execution.dependencies import DependencyResolver


def test_top_level_imports_dedup_and_relative_skipped():
    code = (
        "import os\n"
        "import numpy as np\n"
        "import numpy.linalg\n"
        "from . import sibling\n"
        "from .pkg import thing\n"
        "from mypkg.sub import x\n"
    )
    imports = DependencyResolver.top_level_imports(code)
    assert "os" in imports
    assert "numpy" in imports
    assert imports.count("numpy") == 1
    assert "sibling" not in imports  # relative import skipped
    assert "mypkg" in imports


def test_resolve_classifies_stdlib_local_and_third_party():
    resolver = DependencyResolver(local_modules={"mypkg"})
    report = resolver.resolve("import os\nimport cv2\nfrom mypkg import a\nimport requests\n")
    assert "os" in report.stdlib
    assert "mypkg" in report.local
    assert set(report.third_party) == {"cv2", "requests"}
    # cv2 maps to opencv-python.
    assert "opencv-python" in report.requirements
    assert "requests" in report.requirements


def test_distribution_mapping():
    resolver = DependencyResolver()
    assert resolver.distribution_for("sklearn") == "scikit-learn"
    assert resolver.distribution_for("PIL") == "Pillow"
    assert resolver.distribution_for("totallyunknownpkg") == "totallyunknownpkg"


def test_update_requirements_appends_new_and_preserves_existing(tmp_path):
    req = tmp_path / "requirements.txt"
    req.write_text("numpy==1.26.0\n")
    resolver = DependencyResolver()
    added = resolver.update_requirements(req, ["numpy", "requests", "cv2"])
    # numpy already pinned -> not re-added or downgraded.
    assert "numpy" not in added
    text = req.read_text()
    assert "numpy==1.26.0" in text
    assert "requests" in text
    assert "cv2" in text
    assert set(added) == {"requests", "cv2"}


def test_update_requirements_creates_file(tmp_path):
    req = tmp_path / "sub" / "requirements.txt"
    resolver = DependencyResolver()
    added = resolver.update_requirements(req, ["flask"])
    assert req.exists()
    assert "flask" in req.read_text()
    assert added == ["flask"]


def test_install_command():
    resolver = DependencyResolver()
    assert resolver.install_command([]) == []
    assert resolver.install_command(["flask"], pip="/x/pip") == [
        "/x/pip", "install", "flask"
    ]


def test_syntax_error_returns_no_imports():
    assert DependencyResolver.top_level_imports("def (:\n") == []
