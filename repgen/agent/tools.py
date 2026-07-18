"""Repository tools the exploration agent can call (text-ReAct protocol).

Every tool returns a compact text observation. Tools operate strictly within the
repository root; path traversal outside the root is rejected.
"""

from __future__ import annotations

import ast
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from .context import ReadSnippet, RetrievedContext
from .repomap import RepoMap
from .training import TrainingLoopVisitor

logger = logging.getLogger("repgen.agent.tools")

# Directories we never explore.
_SKIP_DIRS = {".git", "__pycache__", ".venv", "venv", "node_modules", ".mypy_cache"}


# Description injected into the exploration system prompt.
TOOLS_DESCRIPTION = """\
- repo_map: show the structural map (modules, classes, function signatures) to \
reason about where to look. args: {"path": str?}  (optional path prefix to zoom in)
- search_code: BM25 keyword search over code units. args: {"query": str, "k": int?}
- list_dir: list a directory. args: {"path": str}
- read_file: read a file (optionally a line range). args: {"path": str, "start": int?, "end": int?}
- grep: regex search across the repo. args: {"pattern": str, "max_results": int?}
- find_definition: locate a function/class definition. args: {"symbol": str}
- find_training_loops: list files that contain ML training loops. args: {}
- finish: end exploration. args: {"rationale": str, "files": [str, ...]}"""


class RepoToolbox:
    """Stateful executor for the agent's tool calls over one repository."""

    def __init__(self, repo_path: str, max_obs_chars: int = 4000):
        self.root = Path(repo_path).resolve()
        self.max_obs_chars = max_obs_chars
        self.context = RetrievedContext()
        self._repomap: Optional[RepoMap] = None

    # -- helpers ----------------------------------------------------------
    def _safe_path(self, rel: str) -> Path:
        candidate = (self.root / rel).resolve()
        if self.root not in candidate.parents and candidate != self.root:
            raise ValueError(f"Path '{rel}' escapes the repository root.")
        return candidate

    def _rel(self, path: Path) -> str:
        try:
            return str(path.relative_to(self.root))
        except ValueError:
            return str(path)

    def _truncate(self, text: str) -> str:
        if len(text) > self.max_obs_chars:
            return text[: self.max_obs_chars] + "\n... (truncated)"
        return text

    def _iter_py_files(self):
        for path in self.root.rglob("*.py"):
            if any(part in _SKIP_DIRS for part in path.parts):
                continue
            yield path

    # -- tools ------------------------------------------------------------
    def list_dir(self, path: str = ".") -> str:
        target = self._safe_path(path)
        if not target.exists() or not target.is_dir():
            return f"Not a directory: {path}"
        entries = []
        for child in sorted(target.iterdir()):
            if child.name in _SKIP_DIRS:
                continue
            entries.append(child.name + ("/" if child.is_dir() else ""))
        return self._truncate("\n".join(entries) or "(empty)")

    def read_file(
        self, path: str, start: Optional[int] = None, end: Optional[int] = None
    ) -> str:
        target = self._safe_path(path)
        if not target.exists() or not target.is_file():
            return f"File not found: {path}"
        try:
            source = target.read_text(encoding="utf-8", errors="replace")
        except Exception as e:  # noqa: BLE001
            return f"Could not read {path}: {e}"

        rel = self._rel(target)
        lines = source.splitlines()
        if start is not None:
            s = max(1, int(start))
            e = int(end) if end else min(len(lines), s + 80)
            snippet = "\n".join(lines[s - 1 : e])
            self.context.add_snippet(ReadSnippet(rel, snippet, s, e))
            body = "\n".join(f"{i}: {ln}" for i, ln in enumerate(lines[s - 1 : e], s))
            return self._truncate(f"# {rel}:{s}-{e}\n{body}")

        # Whole file (record full content for the symbol index).
        self.context.add_snippet(ReadSnippet(rel, source))
        numbered = "\n".join(f"{i}: {ln}" for i, ln in enumerate(lines, 1))
        return self._truncate(f"# {rel}\n{numbered}")

    def grep(self, pattern: str, max_results: int = 40) -> str:
        try:
            regex = re.compile(pattern)
        except re.error as e:
            return f"Invalid regex: {e}"
        hits: List[str] = []
        for path in self._iter_py_files():
            try:
                for i, line in enumerate(
                    path.read_text(encoding="utf-8", errors="replace").splitlines(), 1
                ):
                    if regex.search(line):
                        hits.append(f"{self._rel(path)}:{i}: {line.strip()}")
                        if len(hits) >= max_results:
                            return self._truncate("\n".join(hits) + "\n... (more)")
            except Exception:  # noqa: BLE001
                continue
        return self._truncate("\n".join(hits) or "No matches.")

    def find_definition(self, symbol: str) -> str:
        results: List[str] = []
        for path in self._iter_py_files():
            try:
                tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
            except Exception:  # noqa: BLE001
                continue
            for node in ast.walk(tree):
                if (
                    isinstance(
                        node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
                    )
                    and node.name == symbol
                ):
                    kind = "class" if isinstance(node, ast.ClassDef) else "def"
                    results.append(f"{self._rel(path)}:{node.lineno}: {kind} {symbol}")
        return self._truncate("\n".join(results) or f"No definition of '{symbol}'.")

    def find_training_loops(self) -> str:
        found: List[str] = []
        for path in self._iter_py_files():
            try:
                tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
            except Exception:  # noqa: BLE001
                continue
            visitor = TrainingLoopVisitor()
            visitor.visit(tree)
            if visitor.found_training:
                found.append(self._rel(path))
        return self._truncate(
            "\n".join(found) or "No training loops detected (heuristic)."
        )

    # -- structural map + BM25 search (dependency-free) ------------------
    @property
    def repomap(self) -> RepoMap:
        if self._repomap is None:
            self._repomap = RepoMap(str(self.root)).build()
        return self._repomap

    def map_overview(self, budget: int = 5000) -> str:
        """A budgeted structural map used to seed the agent's reasoning."""
        return self.repomap.render(budget=budget)

    def repo_map(self, path: Optional[str] = None) -> str:
        return self._truncate(self.repomap.render(budget=8000, prefix=path))

    def search_code(self, query: str, k: int = 8) -> str:
        results = self.repomap.search(query, top_k=k)
        if not results:
            return "No results."
        blocks = []
        for chunk, score in results:
            head = "\n".join(chunk.text.strip().splitlines()[:6])
            blocks.append(
                f"## {chunk.path}:{chunk.start}-{chunk.end} ({chunk.name}) "
                f"[score={score:.2f}]\n{head}"
            )
        return self._truncate("\n\n".join(blocks))

    # -- dispatch ---------------------------------------------------------
    def dispatch(self, tool: str, args: Dict[str, Any]) -> str:
        """Execute a tool call and return its observation string."""
        args = args or {}
        try:
            if tool == "repo_map":
                return self.repo_map(args.get("path"))
            if tool == "search_code":
                return self.search_code(args["query"], int(args.get("k", 8)))
            if tool == "list_dir":
                return self.list_dir(args.get("path", "."))
            if tool == "read_file":
                return self.read_file(args["path"], args.get("start"), args.get("end"))
            if tool == "grep":
                return self.grep(args["pattern"], int(args.get("max_results", 40)))
            if tool == "find_definition":
                return self.find_definition(args["symbol"])
            if tool == "find_training_loops":
                return self.find_training_loops()
            return f"Unknown tool: {tool}"
        except KeyError as e:
            return f"Missing required argument for {tool}: {e}"
        except ValueError as e:
            return f"Error: {e}"
        except Exception as e:  # noqa: BLE001
            logger.warning("Tool %s failed: %s", tool, e)
            return f"Tool {tool} error: {e}"
