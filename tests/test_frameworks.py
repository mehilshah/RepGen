"""Tests for the framework registry."""

from __future__ import annotations

import pytest

from repgen.execution.frameworks import (
    FRAMEWORK_NAMES,
    get_framework,
    list_frameworks,
)


def test_all_expected_frameworks_present():
    assert set(FRAMEWORK_NAMES) == {
        "plain", "fastapi", "flask", "django", "streamlit"
    }


def test_get_framework_default_is_plain():
    assert get_framework(None).name == "plain"
    assert get_framework("").name == "plain"


def test_get_framework_case_insensitive():
    assert get_framework("FastAPI").name == "fastapi"


def test_unknown_framework_raises():
    with pytest.raises(ValueError):
        get_framework("rails")


def test_run_command_substitution():
    fw = get_framework("fastapi")
    cmd = fw.run_command("/venv/python", "/run/app.py")
    assert cmd[0] == "/venv/python"
    assert "uvicorn" in cmd
    assert "app:app" in cmd


def test_plain_run_command():
    fw = get_framework("plain")
    assert fw.run_command("/py", "/x/main.py") == ["/py", "/x/main.py"]


def test_each_framework_has_scaffold_or_deps():
    for fw in list_frameworks():
        assert fw.entrypoint
        # Every framework declares a test command template.
        assert fw.test_argv("/py")[0] == "/py"
