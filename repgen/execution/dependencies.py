"""Automatic third-party dependency detection for generated scripts.

Given a Python source string (a generated reproduction script or user code),
:class:`DependencyResolver` statically discovers the top-level modules it
imports, drops the standard library and modules that belong to the target
repository, maps the remaining *import names* to their PyPI *distribution
names* (e.g. ``cv2`` -> ``opencv-python``), and merges the result into a
``requirements.txt``.

Detection is purely static (AST based) — nothing is imported or executed here.
The install itself happens later in :mod:`repgen.execution.environment`.
"""

from __future__ import annotations

import ast
import logging
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set

logger = logging.getLogger("repgen.execution.dependencies")

# Import name -> PyPI distribution name for the common cases where they differ.
# Kept small and pragmatic; unknown imports fall back to the import name itself.
IMPORT_TO_DISTRIBUTION: Dict[str, str] = {
    "cv2": "opencv-python",
    "PIL": "Pillow",
    "sklearn": "scikit-learn",
    "skimage": "scikit-image",
    "yaml": "PyYAML",
    "bs4": "beautifulsoup4",
    "dotenv": "python-dotenv",
    "dateutil": "python-dateutil",
    "google": "google-api-python-client",
    "OpenSSL": "pyOpenSSL",
    "Crypto": "pycryptodome",
    "serial": "pyserial",
    "usb": "pyusb",
    "win32api": "pywin32",
    "jwt": "PyJWT",
    "attr": "attrs",
    "pkg_resources": "setuptools",
    "lxml": "lxml",
    "torch": "torch",
    "tensorflow": "tensorflow",
    "np": "numpy",  # unusual, but occasionally written as a real import alias target
    "matplotlib": "matplotlib",
    "mpl_toolkits": "matplotlib",
    "PyQt5": "PyQt5",
    "zmq": "pyzmq",
    "redis": "redis",
    "psycopg2": "psycopg2-binary",
    "MySQLdb": "mysqlclient",
    "faiss": "faiss-cpu",
    "grpc": "grpcio",
    "docx": "python-docx",
    "pptx": "python-pptx",
    "fitz": "PyMuPDF",
    "magic": "python-magic",
}

# A curated set of common third-party top-level import names. Used only as a
# hint so we can still flag well-known packages when stdlib detection is
# unavailable; membership here is *not* required for a package to be detected.
_KNOWN_THIRD_PARTY: Set[str] = {
    "numpy",
    "pandas",
    "scipy",
    "requests",
    "flask",
    "django",
    "fastapi",
    "starlette",
    "uvicorn",
    "pydantic",
    "streamlit",
    "click",
    "typer",
    "rich",
    "sqlalchemy",
    "pytest",
    "aiohttp",
    "httpx",
    "transformers",
    "datasets",
    "tqdm",
    "pillow",
    "matplotlib",
    "seaborn",
    "plotly",
    "boto3",
    "openai",
    "anthropic",
}


def _stdlib_modules() -> Set[str]:
    """Best-effort set of standard-library top-level module names."""
    names = getattr(sys, "stdlib_module_names", None)
    if names:
        return set(names)
    # Fallback for <3.10: a conservative, commonly-used subset.
    return {
        "abc", "argparse", "ast", "asyncio", "base64", "collections", "contextlib",
        "copy", "csv", "dataclasses", "datetime", "decimal", "enum", "functools",
        "glob", "hashlib", "heapq", "hmac", "html", "http", "importlib", "inspect",
        "io", "itertools", "json", "logging", "math", "multiprocessing", "os",
        "pathlib", "pickle", "queue", "random", "re", "shutil", "signal", "socket",
        "sqlite3", "ssl", "string", "struct", "subprocess", "sys", "tempfile",
        "textwrap", "threading", "time", "traceback", "typing", "unittest",
        "urllib", "uuid", "warnings", "weakref", "xml", "zipfile", "zlib",
    }


_VERSION_SPEC_RE = re.compile(r"^([A-Za-z0-9_.\-]+)")


@dataclass
class DependencyReport:
    """Outcome of dependency detection for a piece of code."""

    imports: List[str] = field(default_factory=list)  # raw top-level import names
    third_party: List[str] = field(default_factory=list)  # import names, filtered
    requirements: List[str] = field(default_factory=list)  # PyPI dist names
    stdlib: List[str] = field(default_factory=list)
    local: List[str] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not self.requirements

    def render(self) -> str:
        if not self.requirements:
            return "No third-party dependencies detected (standard library only)."
        return "Detected dependencies: " + ", ".join(self.requirements)


class DependencyResolver:
    """Detects third-party dependencies from source and manages requirements.txt."""

    def __init__(
        self,
        local_modules: Optional[Iterable[str]] = None,
        import_map: Optional[Dict[str, str]] = None,
    ):
        # Top-level names that belong to the target repo (never installed).
        self.local_modules: Set[str] = set(local_modules or ())
        self.import_map = {**IMPORT_TO_DISTRIBUTION, **(import_map or {})}
        self._stdlib = _stdlib_modules()

    # -- discovery --------------------------------------------------------
    @staticmethod
    def top_level_imports(code: str) -> List[str]:
        """Return the distinct top-level module names imported by ``code``."""
        try:
            tree = ast.parse(code)
        except SyntaxError:
            logger.debug("Could not parse code for imports; returning empty set.")
            return []
        found: List[str] = []
        seen: Set[str] = set()
        for node in ast.walk(tree):
            names: List[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                # Skip relative imports (level > 0) — they are always local.
                if node.level and node.level > 0:
                    continue
                if node.module:
                    names = [node.module]
            for name in names:
                top = name.split(".")[0]
                if top and top not in seen:
                    seen.add(top)
                    found.append(top)
        return found

    def resolve(self, code: str) -> DependencyReport:
        """Classify imports and produce a set of PyPI requirements."""
        imports = self.top_level_imports(code)
        report = DependencyReport(imports=list(imports))
        for name in imports:
            if name in self._stdlib:
                report.stdlib.append(name)
            elif name in self.local_modules:
                report.local.append(name)
            else:
                report.third_party.append(name)
                report.requirements.append(self.distribution_for(name))
        # De-duplicate requirements while preserving order.
        report.requirements = _dedupe(report.requirements)
        logger.debug("Dependency report: %s", report.render())
        return report

    def distribution_for(self, import_name: str) -> str:
        """Map a top-level import name to its PyPI distribution name."""
        return self.import_map.get(import_name, import_name)

    # -- requirements.txt management -------------------------------------
    @staticmethod
    def parse_requirements(path: Path) -> Dict[str, str]:
        """Parse an existing requirements file into ``{dist_lower: original_line}``."""
        existing: Dict[str, str] = {}
        if not path.exists():
            return existing
        for raw in path.read_text().splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or line.startswith("-"):
                continue
            match = _VERSION_SPEC_RE.match(line)
            if match:
                existing[match.group(1).lower()] = line
        return existing

    def update_requirements(
        self, path: Path, requirements: Iterable[str]
    ) -> List[str]:
        """Merge ``requirements`` into the file at ``path``.

        Never downgrades or clobbers an existing pin — a requirement already
        present (by distribution name) is left untouched. Returns the list of
        newly-added distribution names.
        """
        existing = self.parse_requirements(path)
        added: List[str] = []
        new_lines: List[str] = []
        for req in requirements:
            key = _VERSION_SPEC_RE.match(req)
            key_name = key.group(1).lower() if key else req.lower()
            if key_name in existing:
                continue
            existing[key_name] = req
            new_lines.append(req)
            added.append(req)

        if new_lines:
            path.parent.mkdir(parents=True, exist_ok=True)
            prefix = ""
            if path.exists():
                current = path.read_text()
                if current and not current.endswith("\n"):
                    prefix = "\n"
            else:
                new_lines = ["# Managed by RepGen — auto-detected dependencies"] + new_lines
            with open(path, "a", encoding="utf-8") as f:
                f.write(prefix + "\n".join(new_lines) + "\n")
            logger.info("Added %d requirement(s) to %s", len(added), path)
        return added

    def install_command(
        self, requirements: Iterable[str], pip: str = "pip"
    ) -> List[str]:
        """Build a ``pip install`` argv for the given requirements."""
        reqs = list(requirements)
        if not reqs:
            return []
        return [pip, "install", *reqs]


def _dedupe(items: Iterable[str]) -> List[str]:
    seen: Set[str] = set()
    out: List[str] = []
    for item in items:
        key = item.lower()
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out
