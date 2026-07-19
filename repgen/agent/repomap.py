"""Organized codebase context for LLM-driven (dynamic) retrieval.

Rather than ranking code by static neural-embedding similarity, RepGen gives the
LLM an *organized structural view* of the repository — a "repo map" of modules,
classes, and function signatures — so it can reason about where to look, and a
cheap dependency-free BM25 index for keyword lookups. Semantic judgement is made
by the model, dynamically, as it explores.
"""

from __future__ import annotations

import ast
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

_SKIP_DIRS = {".git", "__pycache__", ".venv", "venv", "node_modules", ".mypy_cache"}


_WORD_RE = re.compile(r"\w+")
# Splits an identifier into its camelCase / PascalCase / digit components.
# e.g. "RotaryEmbedding" -> ["Rotary", "Embedding"], "apply2d" -> ["apply", "2"].
_CAMEL_RE = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|\d+")


def _subtokens(word: str) -> List[str]:
    """Break an identifier into lowercased camelCase / snake_case parts."""
    return [m.group(0).lower() for m in _CAMEL_RE.finditer(word)]


def tokenize(text: str) -> List[str]:
    """Identifier-aware tokenizer used for BM25 and matching.

    Emits both the whole lowercased identifier *and* its sub-components so that
    a query like ``rotary`` or ``apply_rotary_pos_emb`` matches a symbol named
    ``RotaryEmbedding`` (and vice versa). Code search lives or dies on this:
    without it, ``TransformerWrapper`` is a single opaque token that only an
    exact-spelling query can ever hit.
    """
    tokens: List[str] = []
    for raw in _WORD_RE.findall(text):
        low = raw.lower()
        tokens.append(low)
        parts = _subtokens(raw)
        if len(parts) > 1:  # only add parts when they differ from the whole
            tokens.extend(parts)
    return tokens


def index_tokens(rel: str, name: str, text: str) -> List[str]:
    """Tokens for one indexed chunk, weighting the symbol name and path.

    A hit on the symbol's *name* is far more relevant than an incidental hit in
    the body, so we repeat name/path tokens to lift their term frequency —
    cheap field weighting without leaving pure-Python BM25.
    """
    return tokenize(name) * 3 + tokenize(rel) * 2 + tokenize(text)


# ==========================================================================
# BM25 (pure Python, no numpy / rank_bm25 dependency)
# ==========================================================================


class BM25:
    """Okapi BM25 over a fixed corpus of pre-tokenized documents."""

    def __init__(self, corpus: List[List[str]], k1: float = 1.5, b: float = 0.5):
        self.corpus = corpus
        self.k1 = k1
        self.b = b
        self.n = len(corpus)
        self.doc_len = [len(d) for d in corpus]
        self.avgdl = (sum(self.doc_len) / self.n) if self.n else 0.0
        self.tf: List[Counter] = [Counter(d) for d in corpus]
        df: Counter = Counter()
        for doc in corpus:
            df.update(set(doc))
        # Standard BM25 idf with the +1 smoothing to keep scores non-negative.
        self.idf = {
            term: math.log(1 + (self.n - freq + 0.5) / (freq + 0.5))
            for term, freq in df.items()
        }

    def _score(self, query: List[str], index: int) -> float:
        freqs = self.tf[index]
        dl = self.doc_len[index]
        score = 0.0
        for term in query:
            f = freqs.get(term)
            if not f:
                continue
            idf = self.idf.get(term, 0.0)
            denom = f + self.k1 * (1 - self.b + self.b * dl / (self.avgdl or 1))
            score += idf * (f * (self.k1 + 1)) / denom
        return score

    def rank(self, query: List[str], top_k: int) -> List[Tuple[int, float]]:
        scored = [(i, self._score(query, i)) for i in range(self.n)]
        scored = [pair for pair in scored if pair[1] > 0]
        scored.sort(key=lambda p: p[1], reverse=True)
        return scored[:top_k]


# ==========================================================================
# Structural outlines
# ==========================================================================


def _format_args(args: ast.arguments) -> str:
    names = [a.arg for a in args.posonlyargs] + [a.arg for a in args.args]
    if args.vararg:
        names.append("*" + args.vararg.arg)
    names += [a.arg for a in args.kwonlyargs]
    if args.kwarg:
        names.append("**" + args.kwarg.arg)
    return ", ".join(names)


def _first_doc_line(node: ast.AST) -> str:
    doc = ast.get_docstring(node)
    if not doc:
        return ""
    return doc.strip().splitlines()[0][:100]


@dataclass
class Chunk:
    """A retrievable unit of code (a top-level function/class or whole file)."""

    path: str
    name: str
    start: int
    end: int
    text: str


@dataclass
class FileOutline:
    path: str
    doc: str = ""
    classes: List[Tuple[str, str, List[str], str]] = field(default_factory=list)
    functions: List[Tuple[str, str, str]] = field(default_factory=list)

    def render(self) -> str:
        lines = [self.path]
        if self.doc:
            lines.append(f"  “{self.doc}”")
        for name, sig, methods, cdoc in self.classes:
            suffix = f"  # {cdoc}" if cdoc else ""
            lines.append(f"  class {name}({sig}){suffix}")
            if methods:
                lines.append(f"      methods: {', '.join(methods)}")
        for name, sig, fdoc in self.functions:
            suffix = f"  # {fdoc}" if fdoc else ""
            lines.append(f"  def {name}({sig}){suffix}")
        return "\n".join(lines)


class RepoMap:
    """Builds and serves the structural map + BM25 index for a repository."""

    def __init__(self, root: str):
        self.root = Path(root).resolve()
        self.outlines: Dict[str, FileOutline] = {}
        self.chunks: List[Chunk] = []
        self._bm25: Optional[BM25] = None
        self._built = False

    # -- building ---------------------------------------------------------
    def _iter_py_files(self):
        for path in sorted(self.root.rglob("*.py")):
            if any(part in _SKIP_DIRS for part in path.parts):
                continue
            yield path

    def _rel(self, path: Path) -> str:
        try:
            return str(path.relative_to(self.root))
        except ValueError:
            return str(path)

    def build(self) -> "RepoMap":
        if self._built:
            return self
        corpus: List[List[str]] = []
        for path in self._iter_py_files():
            try:
                source = path.read_text(encoding="utf-8", errors="replace")
                tree = ast.parse(source)
            except (OSError, SyntaxError):
                continue
            rel = self._rel(path)
            outline = FileOutline(path=rel, doc=_first_doc_line(tree))
            found_symbol = False
            for node in tree.body:
                if isinstance(node, ast.ClassDef):
                    found_symbol = True
                    methods = [
                        n.name
                        for n in node.body
                        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                    ]
                    init = next(
                        (
                            n
                            for n in node.body
                            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                            and n.name == "__init__"
                        ),
                        None,
                    )
                    sig = _format_args(init.args) if init else ""
                    sig = re.sub(r"\bself,?\s*", "", sig).strip().strip(",").strip()
                    outline.classes.append(
                        (node.name, sig, methods, _first_doc_line(node))
                    )
                    self._add_chunk(rel, node, source, corpus)
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    found_symbol = True
                    outline.functions.append(
                        (node.name, _format_args(node.args), _first_doc_line(node))
                    )
                    self._add_chunk(rel, node, source, corpus)
            self.outlines[rel] = outline
            if not found_symbol:
                # Index the whole file so scripts/configs are still searchable.
                chunk = Chunk(rel, rel, 1, len(source.splitlines()), source)
                self.chunks.append(chunk)
                corpus.append(index_tokens(rel, rel, source))

        self._bm25 = BM25(corpus)
        self._built = True
        return self

    def _add_chunk(
        self, rel: str, node: ast.AST, source: str, corpus: List[List[str]]
    ) -> None:
        text = ast.get_source_segment(source, node) or ""
        chunk = Chunk(
            path=rel,
            name=node.name,
            start=node.lineno,
            end=getattr(node, "end_lineno", node.lineno),
            text=text,
        )
        self.chunks.append(chunk)
        corpus.append(index_tokens(rel, node.name, text))

    # -- serving ----------------------------------------------------------
    def search(self, query: str, top_k: int = 8) -> List[Tuple[Chunk, float]]:
        self.build()
        if not self._bm25 or not self.chunks:
            return []
        ranked = self._bm25.rank(tokenize(query), top_k)
        return [(self.chunks[i], score) for i, score in ranked]

    def outline(self, path: str) -> Optional[str]:
        self.build()
        outline = self.outlines.get(path)
        return outline.render() if outline else None

    def render(self, budget: int = 6000, prefix: Optional[str] = None) -> str:
        """Render a compact, budgeted structural map of the repository."""
        self.build()
        blocks: List[str] = []
        total = 0
        for rel, outline in self.outlines.items():
            if prefix and not rel.startswith(prefix):
                continue
            block = outline.render()
            total += len(block)
            if total > budget:
                blocks.append("... (map truncated; use repo_map with a path prefix)")
                break
            blocks.append(block)
        return "\n".join(blocks) or "(no Python modules found)"
