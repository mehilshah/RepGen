"""Open or create local Python projects.

A :class:`LocalProject` is a thin, framework-aware wrapper over a directory on
disk. ``open_project`` adopts an existing folder (detecting its top-level
importable modules so the dependency resolver can tell repo code from PyPI
packages), while ``create_project`` scaffolds a new one from a
:class:`~repgen.execution.frameworks.Framework` template.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from ..execution.frameworks import Framework, get_framework

logger = logging.getLogger("repgen.projects.local")

# Directories that never contain the project's own importable modules.
_IGNORE_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    ".venv",
    "venv",
    "env",
    ".mypy_cache",
    ".pytest_cache",
    "node_modules",
    "build",
    "dist",
    ".tox",
    ".eggs",
    "site-packages",
    ".idea",
    ".vscode",
}


@dataclass
class LocalProject:
    """A local Python project directory."""

    path: Path
    framework: str = "plain"
    created: bool = False
    local_modules: List[str] = field(default_factory=list)

    @property
    def requirements_path(self) -> Path:
        return self.path / "requirements.txt"

    def as_repo_source(self) -> str:
        """Return the absolute path string used as a repo source downstream."""
        return str(self.path.resolve())


def discover_local_modules(root: Path) -> List[str]:
    """Top-level importable module/package names defined directly in ``root``.

    These are the names the dependency resolver must treat as *local* (never
    ``pip install``-ed). We look one level deep: top-level ``*.py`` files and
    directories containing ``__init__.py`` (or any ``*.py``, to also catch
    implicit-namespace / src-less layouts).
    """
    modules: List[str] = []
    if not root.exists():
        return modules
    for child in sorted(root.iterdir()):
        if child.name.startswith(".") or child.name in _IGNORE_DIRS:
            continue
        if child.is_file() and child.suffix == ".py" and child.stem != "setup":
            modules.append(child.stem)
        elif child.is_dir():
            has_py = any(p.suffix == ".py" for p in child.glob("*.py"))
            if has_py:
                modules.append(child.name)
    # Also peek into a conventional src/ layout.
    src = root / "src"
    if src.is_dir():
        for child in sorted(src.iterdir()):
            if child.is_dir() and any(child.glob("*.py")):
                modules.append(child.name)
            elif child.is_file() and child.suffix == ".py":
                modules.append(child.stem)
    return sorted(set(modules))


def open_project(path: str, framework: Optional[str] = None) -> LocalProject:
    """Open an existing local project directory."""
    root = Path(path).expanduser().resolve()
    if not root.exists():
        raise FileNotFoundError(f"Project path not found: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"Project path is not a directory: {root}")
    fw = _detect_framework(root) if framework is None else framework
    modules = discover_local_modules(root)
    logger.info("Opened local project %s (framework=%s)", root, fw)
    return LocalProject(path=root, framework=fw, created=False, local_modules=modules)


def create_project(
    path: str,
    framework: str = "plain",
    *,
    exist_ok: bool = False,
) -> LocalProject:
    """Create and scaffold a new local project for ``framework``."""
    root = Path(path).expanduser().resolve()
    fw: Framework = get_framework(framework)
    if root.exists() and any(root.iterdir()) and not exist_ok:
        raise FileExistsError(
            f"Directory {root} already exists and is not empty. "
            "Use --force to scaffold into it anyway."
        )
    root.mkdir(parents=True, exist_ok=True)
    for sf in fw.scaffold:
        target = root / sf.path
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and not exist_ok:
            continue
        target.write_text(sf.content)
    logger.info("Created %s project at %s", fw.display_name, root)
    modules = discover_local_modules(root)
    return LocalProject(
        path=root, framework=fw.name, created=True, local_modules=modules
    )


def _detect_framework(root: Path) -> str:
    """Guess the project's framework from its files/requirements (best effort)."""
    req = root / "requirements.txt"
    text = req.read_text().lower() if req.exists() else ""
    pyproject = root / "pyproject.toml"
    if pyproject.exists():
        text += "\n" + pyproject.read_text().lower()

    if (root / "manage.py").exists() or "django" in text:
        return "django"
    if "streamlit" in text:
        return "streamlit"
    if "fastapi" in text:
        return "fastapi"
    if "flask" in text:
        return "flask"
    return "plain"
