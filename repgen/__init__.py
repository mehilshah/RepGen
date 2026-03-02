from typing import Optional

from .core import RepGenService


def reproduce(
    bug_report_source: str,
    repo_source: str,
    backend: str,
    model: str,
    api_key: Optional[str] = None,
    commit: Optional[str] = None,
    output_dir: str = "./repgen_results",
) -> str:
    """
    Generates a reproduction script for a given bug report and repository.

    Args:
        bug_report_source: URL or path to the bug report.
        repo_source: URL or path to the repository.
        backend: The LLM backend to use (openai, gemini, claude).
        model: The model name to use.
        api_key: API key for the backend (optional).
        commit: Specific commit hash to checkout (optional).
        output_dir: Directory to store intermediate artifacts (default: "./repgen_results").

    Returns:
        The generated reproduction script as a string.

    Raises:
        RuntimeError: If reproduction fails.
    """
    service = RepGenService(output_dir=output_dir)
    result = service.run_reproduction(
        bug_report_source=bug_report_source,
        repo_source=repo_source,
        backend=backend,
        model=model,
        commit=commit,
        api_key=api_key,
    )

    if result["success"] and result["files"]:
        # Return the content of the first generated file (usually the reproduction script)
        return result["files"][0]["content"]
    else:
        error_msg = result.get("error", "Unknown error during reproduction")
        raise RuntimeError(f"Reproduction failed: {error_msg}")


__all__ = ["reproduce", "RepGenService"]
