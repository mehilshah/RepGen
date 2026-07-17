"""Artifacts produced by exploration and consumed by generation/verification.

``RetrievedContext`` is the human/LLM-facing bundle of code the agent chose to
read. ``SymbolIndex`` is the machine-facing map of module -> symbol -> signature
that powers the pseudo-symbolic verifier.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class Signature:
    """A lightweight, statically-extracted callable signature."""

    name: str
    kind: str  # "function" | "class" | "method"
    module: str  # dotted module path (derived from the file path)
    params: List[str] = field(default_factory=list)  # positional-or-keyword names
    required: List[str] = field(default_factory=list)  # params without defaults
    has_varargs: bool = False
    has_kwargs: bool = False

    def render(self) -> str:
        parts = list(self.params)
        if self.has_varargs:
            parts.append("*args")
        if self.has_kwargs:
            parts.append("**kwargs")
        return f"{self.name}({', '.join(parts)})"


def _module_from_path(rel_path: str) -> str:
    rel = rel_path.replace("\\", "/")
    if rel.endswith(".py"):
        rel = rel[:-3]
    if rel.endswith("/__init__"):
        rel = rel[: -len("/__init__")]
    return rel.strip("/").replace("/", ".")


def _extract_signature(node: ast.AST, module: str, kind: str) -> Optional[Signature]:
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return None

    if isinstance(node, ast.ClassDef):
        # Use __init__ params (minus self) as the constructor signature.
        init = next(
            (
                n
                for n in node.body
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                and n.name == "__init__"
            ),
            None,
        )
        if init is None:
            return Signature(name=node.name, kind="class", module=module)
        sig = _args_to_signature(init.args, node.name, "class", module)
        return sig

    return _args_to_signature(node.args, node.name, kind, module)


def _args_to_signature(
    args: ast.arguments, name: str, kind: str, module: str
) -> Signature:
    positional = [a.arg for a in args.posonlyargs] + [a.arg for a in args.args]
    kwonly = [a.arg for a in args.kwonlyargs]
    # Drop the receiver for methods/classes.
    if kind in ("class", "method") and positional and positional[0] in ("self", "cls"):
        positional = positional[1:]

    all_params = positional + kwonly

    # Required = params without defaults.
    num_pos_defaults = len(args.defaults)
    pos_required = (
        positional[: len(positional) - num_pos_defaults] if positional else []
    )
    kw_required = [
        a.arg for a, d in zip(args.kwonlyargs, args.kw_defaults) if d is None
    ]
    required = [p for p in pos_required if p not in ("self", "cls")] + kw_required

    return Signature(
        name=name,
        kind=kind,
        module=module,
        params=all_params,
        required=required,
        has_varargs=args.vararg is not None,
        has_kwargs=args.kwarg is not None,
    )


@dataclass
class SymbolIndex:
    """Map of dotted module -> {symbol name -> Signature}."""

    modules: Dict[str, Dict[str, Signature]] = field(default_factory=dict)
    _flat: Dict[str, Signature] = field(default_factory=dict)

    def add_file(self, rel_path: str, source: str) -> None:
        """AST-parse a file and record its top-level defs (best effort)."""
        module = _module_from_path(rel_path)
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return
        bucket = self.modules.setdefault(module, {})
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                kind = "class" if isinstance(node, ast.ClassDef) else "function"
                sig = _extract_signature(node, module, kind)
                if sig:
                    bucket[node.name] = sig
                    self._flat[node.name] = sig

    def module_symbols(self, module: str) -> Dict[str, Signature]:
        """Return symbols for a module, matching by suffix if needed."""
        if module in self.modules:
            return self.modules[module]
        # Fall back to suffix match (e.g. "models.inception" vs "inception").
        for mod, syms in self.modules.items():
            if mod.endswith("." + module) or mod == module:
                return syms
        return {}

    def lookup(self, symbol: str, module: Optional[str] = None) -> Optional[Signature]:
        if module:
            syms = self.module_symbols(module)
            if symbol in syms:
                return syms[symbol]
        return self._flat.get(symbol)

    def all_symbols(self) -> Dict[str, Signature]:
        return dict(self._flat)


@dataclass
class ReadSnippet:
    path: str
    content: str
    start: Optional[int] = None
    end: Optional[int] = None


@dataclass
class RetrievedContext:
    """Ordered bundle of code the agent chose, plus its rationale."""

    rationale: str = ""
    snippets: List[ReadSnippet] = field(default_factory=list)
    key_files: List[str] = field(default_factory=list)
    symbol_index: SymbolIndex = field(default_factory=SymbolIndex)

    def add_snippet(self, snippet: ReadSnippet) -> None:
        self.snippets.append(snippet)
        self.symbol_index.add_file(snippet.path, snippet.content)

    def as_prompt_text(self, max_chars: int = 24000) -> str:
        """Render the gathered context for a generation prompt."""
        blocks: List[str] = []
        if self.rationale:
            blocks.append(f"# Exploration rationale\n{self.rationale}")
        # Prefer key files, then remaining snippets, de-duplicated by path+range.
        seen = set()
        ordered = sorted(
            self.snippets,
            key=lambda s: (s.path not in self.key_files, s.path),
        )
        for snip in ordered:
            marker = (snip.path, snip.start, snip.end)
            if marker in seen:
                continue
            seen.add(marker)
            loc = snip.path
            if snip.start is not None:
                loc += f":{snip.start}-{snip.end}"
            blocks.append(f"# File: {loc}\n```python\n{snip.content}\n```")
        text = "\n\n".join(blocks)
        if len(text) > max_chars:
            text = text[:max_chars] + "\n# ... (context truncated)"
        return text
