"""RepGen Python API examples.

Run the whole file, or call one of the two functions below. Set the relevant API
key first (e.g. ``export OPENAI_API_KEY=...``), or use the keyless ``ollama``
backend with a local server (``ollama serve`` + ``ollama pull llama3.1``).
"""

from repgen import RepGenService, reproduce

BUG_REPORT = "https://github.com/example/repo/issues/1"
REPO = "https://github.com/example/repo.git"


def simple() -> None:
    """One-liner: return the generated reproduction script as a string."""
    script = reproduce(
        bug_report_source=BUG_REPORT,
        repo_source=REPO,
        backend="openai",  # openai | claude | gemini | openrouter | ollama
        model="gpt-4o",  # optional; each backend has a sensible default
    )
    print(script)


def detailed() -> None:
    """Full run: stream progress and inspect artifacts + verification results."""

    def on_event(event: str, data: dict) -> None:
        # Events include: setup, refine, explore.action, generate.attempt_verified, done
        print(f"[{event}] {data.get('message', '')}")

    service = RepGenService(output_dir="./repgen_results")
    result = service.run_reproduction(
        bug_report_source=BUG_REPORT,
        repo_source=REPO,
        backend="ollama",
        model="llama3.1",
        max_attempts=3,
        max_explore_steps=12,
        progress_callback=on_event,
    )

    print(f"\nVerified: {result['success']}")
    print(f"Run directory: {result['run_dir']}")
    print(f"Report: {result.get('report')}")
    for file_info in result["files"]:
        print(f"Generated: {file_info['path']}")


if __name__ == "__main__":
    try:
        simple()
    except Exception as e:  # noqa: BLE001 - example only
        print(f"Error: {e}")
