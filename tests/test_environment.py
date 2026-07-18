"""Tests for the venv environment manager.

Creating a real venv is done once (it is fast with ``with_pip``); no network is
required because we never install third-party packages here.
"""

from __future__ import annotations

from repgen.execution.environment import EnvironmentManager


def test_prepare_creates_and_reuses_venv(tmp_path):
    mgr = EnvironmentManager(tmp_path)
    env = mgr.prepare()
    assert env.created
    assert env.python.exists()
    assert env.root.exists()
    # Reuse: a second prepare should not recreate.
    env2 = mgr.prepare()
    assert not env2.created
    assert env2.python == env.python


def test_setup_and_run_commands(tmp_path):
    mgr = EnvironmentManager(tmp_path)
    env = mgr.prepare()
    setup = env.setup_command()
    assert "venv" in setup
    run = env.run_command(tmp_path / "x.py", ["--flag"])
    assert str(env.python) == run[0]
    assert "--flag" in run


def test_install_empty_is_noop(tmp_path):
    mgr = EnvironmentManager(tmp_path)
    env = mgr.prepare()
    result = mgr.install(env, [])
    assert result.success
    assert result.skipped


def test_install_missing_requirements_file(tmp_path):
    mgr = EnvironmentManager(tmp_path)
    env = mgr.prepare()
    result = mgr.install_requirements_file(env, tmp_path / "none.txt")
    assert result.success  # nothing to install
