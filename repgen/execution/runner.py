"""Streaming subprocess runner for generated scripts.

:class:`CodeRunner` executes a Python script inside a prepared virtual
environment, streaming stdout/stderr live to a callback while also capturing
them, enforcing a wall-clock timeout, and parsing any Python traceback out of
stderr into a structured :class:`ExecutionResult`.

Separate stdout/stderr streams are preserved (unlike the merged pip stream in
:mod:`environment`) because the reproduction analyzer and UI need to
distinguish program output from errors and tracebacks.
"""

from __future__ import annotations

import logging
import os
import re
import selectors
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional

logger = logging.getLogger("repgen.execution.runner")

# Callback: (line_text, stream) where stream is "stdout" or "stderr".
LineCallback = Optional[Callable[[str, str], None]]

_TRACEBACK_HEADER = "Traceback (most recent call last):"
# Matches the final "ExceptionType: message" line of a traceback.
_EXC_LINE_RE = re.compile(
    r"^([A-Za-z_][\w.]*(?:Error|Exception|Warning|Exit))\b:?(.*)$"
)


@dataclass
class ExecutionResult:
    """Structured result of running a script."""

    returncode: int
    stdout: str = ""
    stderr: str = ""
    duration_s: float = 0.0
    timed_out: bool = False
    exception_type: Optional[str] = None
    exception_message: str = ""
    traceback: str = ""
    command: List[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        """Exited 0 without timing out."""
        return self.returncode == 0 and not self.timed_out

    @property
    def raised(self) -> bool:
        return self.exception_type is not None

    @property
    def combined_output(self) -> str:
        parts = []
        if self.stdout:
            parts.append(self.stdout)
        if self.stderr:
            parts.append(self.stderr)
        return "\n".join(parts)

    def summary(self) -> str:
        if self.timed_out:
            return f"Timed out after {self.duration_s:.1f}s"
        if self.success:
            return f"Exited 0 in {self.duration_s:.1f}s"
        if self.exception_type:
            return (
                f"Exited {self.returncode} in {self.duration_s:.1f}s "
                f"({self.exception_type}: {self.exception_message.strip()[:80]})"
            )
        return f"Exited {self.returncode} in {self.duration_s:.1f}s"


def _parse_traceback(stderr: str) -> tuple[Optional[str], str, str]:
    """Extract ``(exception_type, message, traceback_block)`` from stderr."""
    if _TRACEBACK_HEADER not in stderr:
        # Some tools print an error without a full traceback; try last line.
        return None, "", ""
    idx = stderr.rindex(_TRACEBACK_HEADER)
    block = stderr[idx:]
    lines = [ln for ln in block.splitlines() if ln.strip()]
    # The exception line is the last non-indented line of the block.
    for line in reversed(lines):
        if line.startswith(" "):
            continue
        match = _EXC_LINE_RE.match(line.strip())
        if match:
            return match.group(1), match.group(2).strip(), block
        # A bare "SystemExit" style line with no colon.
        token = line.strip().split(":", 1)[0]
        if token and token[0].isupper():
            return token, line.strip(), block
    return None, "", block


class CodeRunner:
    """Runs a Python script in a venv with streaming and timeout handling."""

    def __init__(self, python: Path):
        self.python = Path(python)

    def run(
        self,
        script: Path,
        *,
        cwd: Optional[Path] = None,
        args: Optional[List[str]] = None,
        timeout: int = 600,
        on_line: LineCallback = None,
        env: Optional[dict] = None,
    ) -> ExecutionResult:
        """Execute ``script`` and return a structured :class:`ExecutionResult`."""
        cmd = [str(self.python), "-u", str(script), *(args or [])]
        run_env = {**os.environ, "PYTHONUNBUFFERED": "1"}
        if env:
            run_env.update(env)

        logger.info("Executing: %s (timeout=%ss)", " ".join(cmd), timeout)
        start = time.time()
        try:
            process = subprocess.Popen(
                cmd,
                cwd=str(cwd) if cwd else None,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                env=run_env,
            )
        except FileNotFoundError as e:
            return ExecutionResult(
                returncode=127,
                stderr=str(e),
                command=cmd,
                exception_type="FileNotFoundError",
                exception_message=str(e),
            )

        stdout_lines, stderr_lines, timed_out = self._pump(
            process, timeout, on_line, start
        )
        duration = time.time() - start
        stdout = "\n".join(stdout_lines)
        stderr = "\n".join(stderr_lines)
        exc_type, exc_msg, tb = _parse_traceback(stderr)
        return ExecutionResult(
            returncode=process.returncode if process.returncode is not None else -1,
            stdout=stdout,
            stderr=stderr,
            duration_s=duration,
            timed_out=timed_out,
            exception_type=exc_type,
            exception_message=exc_msg,
            traceback=tb,
            command=cmd,
        )

    def _pump(
        self,
        process: subprocess.Popen,
        timeout: int,
        on_line: LineCallback,
        start: float,
    ) -> tuple[List[str], List[str], bool]:
        """Stream both pipes concurrently until exit or timeout."""
        stdout_lines: List[str] = []
        stderr_lines: List[str] = []
        timed_out = False

        # selectors gives us concurrent, portable multiplexing of both pipes.
        sel = selectors.DefaultSelector()
        assert process.stdout is not None and process.stderr is not None
        sel.register(process.stdout, selectors.EVENT_READ, "stdout")
        sel.register(process.stderr, selectors.EVENT_READ, "stderr")
        open_streams = 2

        while open_streams > 0:
            if timeout and (time.time() - start) > timeout:
                timed_out = True
                process.kill()
                break
            for key, _ in sel.select(timeout=0.2):
                line = key.fileobj.readline()  # type: ignore[union-attr]
                if line == "":  # EOF on this stream
                    sel.unregister(key.fileobj)
                    open_streams -= 1
                    continue
                text = line.rstrip("\n")
                if key.data == "stdout":
                    stdout_lines.append(text)
                else:
                    stderr_lines.append(text)
                if on_line:
                    on_line(text, key.data)

        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        finally:
            sel.close()
        # Drain anything buffered after kill/exit.
        if not timed_out:
            try:
                rem_out, rem_err = process.communicate(timeout=5)
                for text in (rem_out or "").splitlines():
                    stdout_lines.append(text)
                    if on_line:
                        on_line(text, "stdout")
                for text in (rem_err or "").splitlines():
                    stderr_lines.append(text)
                    if on_line:
                        on_line(text, "stderr")
            except Exception:  # noqa: BLE001 - streams may already be closed
                pass
        return stdout_lines, stderr_lines, timed_out
