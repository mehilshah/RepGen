"""Per-run virtual environment management (host-venv subprocess model).

:class:`EnvironmentManager` creates an isolated ``venv`` for a run, installs the
detected dependencies with live pip output, and exposes the concrete shell
commands (setup / install / execute) so the UI can show exactly what RepGen is
doing — matching the "command visibility" requirement of the redesigned CLI.

Nothing here executes the *generated* code; that is the job of
:class:`repgen.execution.runner.CodeRunner`. This module only builds the
environment the runner will use.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import venv
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional

logger = logging.getLogger("repgen.execution.environment")

# Callback receiving a single line of streamed output plus a stream label
# ("stdout"/"stderr"). Mirrors the progress-callback style used elsewhere.
LineCallback = Optional[Callable[[str, str], None]]


@dataclass
class InstallResult:
    """Outcome of a dependency installation step."""

    success: bool
    requirements: List[str] = field(default_factory=list)
    command: List[str] = field(default_factory=list)
    output: str = ""
    returncode: int = 0

    @property
    def skipped(self) -> bool:
        return not self.requirements


@dataclass
class PreparedEnvironment:
    """A ready-to-use virtual environment for a run."""

    root: Path  # the venv directory
    python: Path  # path to the venv's python executable
    pip: Path  # path to the venv's pip executable
    created: bool = False  # False when we reused an existing venv
    system_site_packages: bool = False
    # Set when the library under test could not be pip-installed (no packaging
    # metadata) and must instead be importable via PYTHONPATH at run time.
    extra_pythonpath: Optional[str] = None

    def setup_command(self) -> List[str]:
        """The command that (re)creates this venv."""
        args = [sys.executable, "-m", "venv"]
        if self.system_site_packages:
            args.append("--system-site-packages")
        args.append(str(self.root))
        return args

    def run_command(self, script: Path, args: Optional[List[str]] = None) -> List[str]:
        """The command that runs ``script`` inside this venv."""
        return [str(self.python), str(script), *(args or [])]


def _venv_bin(root: Path) -> Path:
    return root / ("Scripts" if os.name == "nt" else "bin")


def _venv_python(root: Path) -> Path:
    exe = "python.exe" if os.name == "nt" else "python"
    return _venv_bin(root) / exe


def _venv_pip(root: Path) -> Path:
    exe = "pip.exe" if os.name == "nt" else "pip"
    return _venv_bin(root) / exe


def _stream_subprocess(
    cmd: List[str],
    cwd: Optional[Path],
    on_line: LineCallback,
    env: Optional[dict] = None,
    timeout: Optional[int] = None,
) -> subprocess.CompletedProcess:
    """Run ``cmd`` streaming combined output line-by-line to ``on_line``."""
    logger.debug("Running: %s", " ".join(cmd))
    process = subprocess.Popen(
        cmd,
        cwd=str(cwd) if cwd else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env=env,
    )
    collected: List[str] = []
    assert process.stdout is not None
    try:
        for line in process.stdout:
            line = line.rstrip("\n")
            collected.append(line)
            if on_line:
                on_line(line, "stdout")
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
        raise
    return subprocess.CompletedProcess(
        cmd, process.returncode or 0, stdout="\n".join(collected), stderr=""
    )


class EnvironmentManager:
    """Creates and populates per-run virtual environments."""

    def __init__(
        self,
        base_dir: Path,
        *,
        system_site_packages: bool = False,
        upgrade_pip: bool = False,
    ):
        # Resolve to an absolute path so the venv's python/pip work regardless
        # of the subprocess cwd (pip install runs from the process cwd; the
        # generated script runs with cwd set to the run directory).
        self.base_dir = Path(base_dir).resolve()
        self.system_site_packages = system_site_packages
        self.upgrade_pip = upgrade_pip

    def prepare(
        self,
        name: str = ".venv",
        on_line: LineCallback = None,
        reuse: bool = True,
    ) -> PreparedEnvironment:
        """Create (or reuse) a venv under ``base_dir/name``."""
        root = self.base_dir / name
        python = _venv_python(root)
        already = reuse and python.exists()
        env = PreparedEnvironment(
            root=root,
            python=python,
            pip=_venv_pip(root),
            created=not already,
            system_site_packages=self.system_site_packages,
        )
        if already:
            logger.debug("Reusing existing venv at %s", root)
            return env

        logger.info("Creating venv at %s", root)
        if on_line:
            on_line(f"Creating virtual environment at {root}", "stdout")
        builder = venv.EnvBuilder(
            system_site_packages=self.system_site_packages,
            with_pip=True,
            clear=False,
        )
        builder.create(str(root))
        if self.upgrade_pip:
            self._pip(env, ["install", "--upgrade", "pip"], on_line)
        return env

    def install(
        self,
        env: PreparedEnvironment,
        requirements: List[str],
        on_line: LineCallback = None,
        timeout: Optional[int] = 1800,
    ) -> InstallResult:
        """Install ``requirements`` into the prepared environment (streamed)."""
        if not requirements:
            return InstallResult(success=True, requirements=[])
        cmd = [str(env.pip), "install", *requirements]
        if on_line:
            on_line("$ " + " ".join(cmd), "stdout")
        try:
            completed = _stream_subprocess(
                cmd, cwd=None, on_line=on_line, timeout=timeout
            )
        except subprocess.TimeoutExpired:
            return InstallResult(
                success=False,
                requirements=requirements,
                command=cmd,
                output="pip install timed out",
                returncode=124,
            )
        except FileNotFoundError as e:
            return InstallResult(
                success=False,
                requirements=requirements,
                command=cmd,
                output=str(e),
                returncode=127,
            )
        return InstallResult(
            success=completed.returncode == 0,
            requirements=requirements,
            command=cmd,
            output=completed.stdout,
            returncode=completed.returncode,
        )

    def install_project(
        self,
        env: PreparedEnvironment,
        project_dir: Path,
        on_line: LineCallback = None,
        editable: bool = True,
        timeout: Optional[int] = 1800,
    ) -> InstallResult:
        """Install the target project (the library under test) into ``env``.

        Installs from ``project_dir`` — which the caller has already checked out
        to the commit/date where the bug reproduces — so the library under test
        is present at that exact version and its declared dependencies resolve
        to matching versions. An editable install (``-e``) is used by default so
        the on-disk source is what runs.
        """
        cmd = [str(env.pip), "install"]
        if editable:
            cmd.append("-e")
        cmd.append(str(project_dir))
        if on_line:
            on_line("$ " + " ".join(cmd), "stdout")
        try:
            completed = _stream_subprocess(
                cmd, cwd=None, on_line=on_line, timeout=timeout
            )
        except subprocess.TimeoutExpired:
            return InstallResult(
                success=False,
                command=cmd,
                output="project install timed out",
                returncode=124,
            )
        except FileNotFoundError as e:
            return InstallResult(
                success=False, command=cmd, output=str(e), returncode=127
            )
        return InstallResult(
            success=completed.returncode == 0,
            command=cmd,
            output=completed.stdout,
            returncode=completed.returncode,
        )

    def install_requirements_file(
        self,
        env: PreparedEnvironment,
        requirements_txt: Path,
        on_line: LineCallback = None,
        timeout: Optional[int] = 1800,
    ) -> InstallResult:
        """Install from a ``requirements.txt`` file."""
        if not requirements_txt.exists():
            return InstallResult(success=True, requirements=[])
        cmd = [str(env.pip), "install", "-r", str(requirements_txt)]
        if on_line:
            on_line("$ " + " ".join(cmd), "stdout")
        try:
            completed = _stream_subprocess(
                cmd, cwd=None, on_line=on_line, timeout=timeout
            )
        except subprocess.TimeoutExpired:
            return InstallResult(
                success=False,
                command=cmd,
                output="pip install timed out",
                returncode=124,
            )
        return InstallResult(
            success=completed.returncode == 0,
            command=cmd,
            output=completed.stdout,
            returncode=completed.returncode,
        )

    def _pip(
        self, env: PreparedEnvironment, args: List[str], on_line: LineCallback
    ) -> None:
        try:
            _stream_subprocess([str(env.pip), *args], cwd=None, on_line=on_line)
        except Exception as e:  # noqa: BLE001 - non-fatal (e.g. pip upgrade)
            logger.debug("pip %s failed: %s", args, e)
