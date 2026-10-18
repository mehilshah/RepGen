"""RepGen: exploration-based automated bug reproduction with LLMs."""

from __future__ import annotations

from typing import Optional

__version__ = "1.0.1"

__all__ = ["reproduce", "RepGenService", "__version__"]


def __getattr__(name: str):
    # Lazy imports keep `import repgen` fast and avoid pulling heavy optional
    # dependencies until they are actually needed.
    if name == "RepGenService":
        from .core import RepGenService

        return RepGenService
    raise AttributeError(f"module 'repgen' has no attribute {name!r}")


def reproduce(
    bug_report_source: str,
    repo_source: str,
    backend: str,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    commit: Optional[str] = None,
    output_dir: str = "./repgen_results",
    max_attempts: int = 3,
    max_explore_steps: int = 12,
    execute: bool = False,
    framework: Optional[str] = None,
) -> str:
    """Generate a reproduction script for a bug report + repository.

    Returns the generated script as a string; raises ``RuntimeError`` on failure.

    Pass ``execute=True`` to also plan, build an isolated venv, run the script,
    and verify reproduction (non-interactive: only Quick runs execute
    automatically). The library default is ``False`` to keep ``reproduce`` free
    of side effects such as venv creation.
    """
    from .core import RepGenService

    service = RepGenService(output_dir=output_dir)
    result = service.run_reproduction(
        bug_report_source=bug_report_source,
        repo_source=repo_source,
        backend=backend,
        model=model,
        commit=commit,
        api_key=api_key,
        max_attempts=max_attempts,
        max_explore_steps=max_explore_steps,
        execute=execute,
        framework=framework,
    )
    if result["success"] and result["files"]:
        return result["files"][0]["content"]
    raise RuntimeError(f"Reproduction failed: {result.get('error', 'unknown error')}")
