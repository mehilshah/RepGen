"""Stage 3: pseudo-symbolic execution.

A static AST "abstract interpreter" that reasons about the generated script
*without running it*. It checks four things:

1. Import resolution against the explored ``SymbolIndex`` (does ``from M import Y``
   actually name a symbol that exists in repo module ``M``?).
2. Name binding (undefined-name / no obvious definition), builtins-aware.
3. Call signatures against retrieved definitions (arity + keyword validity).
4. Failure-path reachability: the reported failing API is actually invoked and an
   observation point (assert/print/try-except) is present to surface the bug.
"""

from __future__ import annotations

import ast
import builtins
import sys
from typing import Dict, List, Optional, Tuple

from ..context import Signature, SymbolIndex
from .base import Feedback, Finding, VerificationContext, Verifier

_BUILTINS = set(dir(builtins)) | {
    "__name__",
    "__file__",
    "__doc__",
    "__builtins__",
    "self",
    "cls",
}

# Third-party libraries whose internals we cannot (and should not) resolve.
_KNOWN_THIRD_PARTY = {
    "torch",
    "tensorflow",
    "tf",
    "numpy",
    "np",
    "pandas",
    "pd",
    "sklearn",
    "scipy",
    "keras",
    "jax",
    "transformers",
    "PIL",
    "cv2",
    "matplotlib",
    "pytest",
    "requests",
}

try:
    _STDLIB = set(sys.stdlib_module_names)  # Python 3.10+
except AttributeError:  # pragma: no cover
    _STDLIB = set()


class SymbolicVerifier(Verifier):
    stage = "symbolic"

    def verify(self, code: str, ctx: VerificationContext) -> Feedback:
        try:
            tree = ast.parse(code)
        except SyntaxError:
            # Syntax stage owns this; don't double-report.
            return Feedback(stage=self.stage, passed=True)

        findings: List[Finding] = []
        index = ctx.symbol_index

        from_imports, module_imports, defined = self._collect_bindings(tree)

        findings += self._check_import_resolution(tree, index)
        findings += self._check_undefined_names(
            tree, defined, from_imports, module_imports
        )
        findings += self._check_call_signatures(
            tree, index, from_imports, module_imports
        )
        # Failure-path reachability. Warning-level findings are tagged internally
        # with suggestion == "__warning__" and do not block success.
        findings += self._check_failure_path(tree, ctx)

        real_errors = [f for f in findings if f.suggestion != "__warning__"]
        passed = not real_errors
        severity = "error" if real_errors else ("warning" if findings else "info")
        # Strip the internal warning tag before returning.
        for f in findings:
            if f.suggestion == "__warning__":
                f.suggestion = None
        return Feedback(
            stage=self.stage, passed=passed, severity=severity, findings=findings
        )

    # -- binding collection ----------------------------------------------
    def _collect_bindings(
        self, tree: ast.AST
    ) -> Tuple[Dict[str, Tuple[str, str]], Dict[str, str], set]:
        """Return (from_imports, module_imports, defined_names).

        from_imports: alias -> (module, original_name)
        module_imports: alias -> module (for `import M [as alias]`)
        defined_names: flow-insensitive set of every name bound anywhere.
        """
        from_imports: Dict[str, Tuple[str, str]] = {}
        module_imports: Dict[str, str] = {}
        defined: set = set()

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    bound = alias.asname or alias.name.split(".")[0]
                    module_imports[bound] = alias.name
                    defined.add(bound)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for alias in node.names:
                    if alias.name == "*":
                        continue
                    bound = alias.asname or alias.name
                    from_imports[bound] = (module, alias.name)
                    defined.add(bound)
            elif isinstance(
                node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
            ):
                defined.add(node.name)
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    for arg in (
                        node.args.posonlyargs + node.args.args + node.args.kwonlyargs
                    ):
                        defined.add(arg.arg)
                    if node.args.vararg:
                        defined.add(node.args.vararg.arg)
                    if node.args.kwarg:
                        defined.add(node.args.kwarg.arg)
            elif isinstance(node, (ast.Global, ast.Nonlocal)):
                defined.update(node.names)
            elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                defined.add(node.id)
            elif isinstance(node, (ast.For, ast.AsyncFor, ast.comprehension)):
                defined.update(self._target_names(node.target))
            elif isinstance(node, ast.withitem) and node.optional_vars:
                defined.update(self._target_names(node.optional_vars))
            elif isinstance(node, ast.ExceptHandler) and node.name:
                defined.add(node.name)

        return from_imports, module_imports, defined

    @staticmethod
    def _target_names(target: ast.AST) -> List[str]:
        names = []
        for n in ast.walk(target):
            if isinstance(n, ast.Name):
                names.append(n.id)
        return names

    # -- checks -----------------------------------------------------------
    def _check_import_resolution(
        self, tree: ast.AST, index: SymbolIndex
    ) -> List[Finding]:
        findings: List[Finding] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom) or node.level:
                continue
            module = node.module or ""
            top = module.split(".")[0]
            if top in _STDLIB or top in _KNOWN_THIRD_PARTY:
                continue
            known = index.module_symbols(module)
            if not known:
                continue  # module not explored; cannot verify
            for alias in node.names:
                if alias.name == "*":
                    continue
                if alias.name not in known:
                    suggestion = self._suggest(alias.name, known.keys())
                    findings.append(
                        Finding(
                            message=(
                                f"'{alias.name}' is not defined in module "
                                f"'{module}' (explored symbols: "
                                f"{', '.join(sorted(known)[:8])})"
                            ),
                            line=node.lineno,
                            suggestion=suggestion,
                        )
                    )
        return findings

    def _check_undefined_names(
        self,
        tree: ast.AST,
        defined: set,
        from_imports: Dict[str, Tuple[str, str]],
        module_imports: Dict[str, str],
    ) -> List[Finding]:
        findings: List[Finding] = []
        known = defined | set(from_imports) | set(module_imports) | _BUILTINS
        reported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                if node.id not in known and node.id not in reported:
                    reported.add(node.id)
                    findings.append(
                        Finding(
                            message=f"name '{node.id}' is used but never defined or imported",
                            line=getattr(node, "lineno", None),
                            suggestion="Define it or add the missing import.",
                        )
                    )
        return findings

    def _check_call_signatures(
        self,
        tree: ast.AST,
        index: SymbolIndex,
        from_imports: Dict[str, Tuple[str, str]],
        module_imports: Dict[str, str],
    ) -> List[Finding]:
        findings: List[Finding] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            sig = self._resolve_callee(node.func, index, from_imports, module_imports)
            if sig is None:
                continue
            findings += self._match_signature(node, sig)
        return findings

    def _resolve_callee(
        self,
        func: ast.AST,
        index: SymbolIndex,
        from_imports: Dict[str, Tuple[str, str]],
        module_imports: Dict[str, str],
    ) -> Optional[Signature]:
        if isinstance(func, ast.Name):
            if func.id in from_imports:
                module, orig = from_imports[func.id]
                return index.lookup(orig, module)
            return None
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
            alias = func.value.id
            if alias in module_imports:
                return index.lookup(func.attr, module_imports[alias])
        return None

    def _match_signature(self, call: ast.Call, sig: Signature) -> List[Finding]:
        findings: List[Finding] = []
        has_starargs = any(isinstance(a, ast.Starred) for a in call.args)
        has_kwspread = any(k.arg is None for k in call.keywords)
        positional = [a for a in call.args if not isinstance(a, ast.Starred)]
        kwargs = [k.arg for k in call.keywords if k.arg is not None]

        if not sig.has_varargs and not has_starargs:
            if len(positional) > len(sig.params):
                findings.append(
                    Finding(
                        message=(
                            f"{sig.render()} called with {len(positional)} positional "
                            f"args but accepts at most {len(sig.params)}"
                        ),
                        line=call.lineno,
                        suggestion="Match the retrieved signature.",
                    )
                )

        if not sig.has_kwargs:
            for kw in kwargs:
                if kw not in sig.params:
                    findings.append(
                        Finding(
                            message=f"unexpected keyword argument '{kw}' for {sig.render()}",
                            line=call.lineno,
                            suggestion=self._suggest(kw, sig.params),
                        )
                    )

        if not has_starargs and not has_kwspread:
            provided = set(sig.params[: len(positional)]) | set(kwargs)
            missing = [r for r in sig.required if r not in provided]
            if missing:
                findings.append(
                    Finding(
                        message=(
                            f"missing required argument(s) {missing} for {sig.render()}"
                        ),
                        line=call.lineno,
                        suggestion="Provide the required arguments.",
                    )
                )
        return findings

    def _check_failure_path(
        self, tree: ast.AST, ctx: VerificationContext
    ) -> List[Finding]:
        findings: List[Finding] = []
        sig = ctx.failure_signature
        if sig.is_empty():
            return findings

        called_names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                f = node.func
                if isinstance(f, ast.Name):
                    called_names.add(f.id)
                elif isinstance(f, ast.Attribute):
                    called_names.add(f.attr)

        if sig.trigger_apis:
            if not any(api in called_names for api in sig.trigger_apis):
                findings.append(
                    Finding(
                        message=(
                            "reproduction never invokes the failing operation(s): "
                            f"{sig.trigger_apis}"
                        ),
                        suggestion="Call the API named in the bug report so the bug can manifest.",
                    )
                )

        # Observation point (warning only).
        has_observation = any(
            isinstance(n, (ast.Assert, ast.Try))
            or (
                isinstance(n, ast.Call)
                and isinstance(n.func, ast.Name)
                and n.func.id == "print"
            )
            for n in ast.walk(tree)
        )
        if not has_observation:
            findings.append(
                Finding(
                    message="no observation point (assert/print/try-except) to surface the bug",
                    suggestion="__warning__",
                )
            )
        return findings

    @staticmethod
    def _suggest(name: str, candidates) -> Optional[str]:
        import difflib

        matches = difflib.get_close_matches(name, list(candidates), n=1, cutoff=0.7)
        if matches:
            return f"did you mean '{matches[0]}'?"
        return None
