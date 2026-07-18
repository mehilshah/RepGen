"""Tests for the streaming code runner."""

from __future__ import annotations

import sys
from pathlib import Path

from repgen.execution.runner import CodeRunner, _parse_traceback


def _run(tmp_path, code, **kw):
    script = tmp_path / "s.py"
    script.write_text(code)
    return CodeRunner(Path(sys.executable)).run(script, timeout=30, **kw)


def test_successful_run(tmp_path):
    res = _run(tmp_path, "print('hello')\n")
    assert res.success
    assert res.returncode == 0
    assert "hello" in res.stdout
    assert not res.raised


def test_exception_parsed(tmp_path):
    res = _run(tmp_path, "raise ValueError('boom')\n")
    assert not res.success
    assert res.returncode != 0
    assert res.exception_type == "ValueError"
    assert "boom" in res.exception_message
    assert res.raised
    assert "Traceback" in res.traceback


def test_stdout_stderr_separated(tmp_path):
    res = _run(
        tmp_path,
        "import sys\nprint('out')\nprint('err', file=sys.stderr)\n",
    )
    assert "out" in res.stdout
    assert "err" in res.stderr
    assert "err" not in res.stdout


def test_streaming_callback(tmp_path):
    lines = []
    _run(tmp_path, "print('a')\nprint('b')\n", on_line=lambda l, s: lines.append((s, l)))
    assert ("stdout", "a") in lines
    assert ("stdout", "b") in lines


def test_timeout(tmp_path):
    script = tmp_path / "s.py"
    script.write_text("import time\ntime.sleep(10)\n")
    res = CodeRunner(Path(sys.executable)).run(script, timeout=1)
    assert res.timed_out
    assert not res.success
    assert "Timed out" in res.summary()


def test_missing_interpreter(tmp_path):
    script = tmp_path / "s.py"
    script.write_text("print('x')\n")
    res = CodeRunner(Path("/no/such/python")).run(script, timeout=5)
    assert res.returncode == 127
    assert not res.success


def test_parse_traceback_helper():
    stderr = (
        "Traceback (most recent call last):\n"
        '  File "x.py", line 1, in <module>\n'
        "    raise KeyError('k')\n"
        "KeyError: 'k'\n"
    )
    exc, msg, block = _parse_traceback(stderr)
    assert exc == "KeyError"
    assert "'k'" in msg
    assert "Traceback" in block
