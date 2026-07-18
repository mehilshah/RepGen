# Python API

RepGen can be embedded in Python. The primary entry point is `repgen.reproduce`.

```python
import repgen

script = repgen.reproduce(
    bug_report_source="https://github.com/owner/repo/issues/123",
    repo_source="https://github.com/owner/repo.git",
    backend="openai",          # openai | claude | gemini | openrouter | ollama
    model="gpt-4o",            # optional; defaults per backend
    commit=None,               # optional git commit to check out
    output_dir="./repgen_results",
    max_attempts=3,
    max_explore_steps=12,
    execute=False,             # set True to also run + verify in a venv
    framework=None,            # plain | fastapi | flask | django | streamlit
)
print(script)
```

`reproduce` returns the generated script as a string and raises `RuntimeError`
if no script could be produced. With `execute=True` it additionally plans,
builds an isolated venv, runs the script, and verifies reproduction
(non-interactive: only *Quick* runs execute automatically). The library default
is `False` to keep `reproduce` free of side effects such as venv creation.

## Lower-level: `RepGenService`

For full results (verification attempts, artifact paths, run report) use the
service directly:

```python
from repgen import RepGenService

service = RepGenService(output_dir="./repgen_results")
result = service.run_reproduction(
    bug_report_source="./bug.txt",
    repo_source="./my-repo",
    backend="ollama",
    model="llama3.1",
    progress_callback=lambda event, data: print(event),
)

print(result["success"], result["run_dir"], result["report"])
for f in result["files"]:
    print(f["path"])
```

The `progress_callback` receives `(event, data)` tuples for setup, refinement,
exploration (`explore.action`, `explore.observation`, …), and generation
(`generate.attempt_verified`, …) — the CLI uses this to render its live view.

To fully drive execution (planning, gating, refine/retry) with your own UI,
pass `execute=True` plus an `exec_progress_callback` and, for interactive
Medium/Large gating, a `confirm_callback` returning an `ExecutionDecision`.
`result["execution"]` then holds an `ExecutionOutcome` (plan, attempts, verdict).

## Backends

```python
from repgen.backends import get_backend, list_backends

client = get_backend("claude")  # defaults to claude-opus-4-8
print(client.is_configured(), client.list_models())
response = client.generate("Say hi.")
print(response.text)
```

## Execution engine

```python
from repgen.execution import (
    ExecutionPipeline, ExecutionSettings, detect_hardware, DependencyResolver,
)

# Inspect what would run, without executing:
deps = DependencyResolver().resolve(open("reproduce.py").read())
print(deps.render())          # detected PyPI requirements
print(detect_hardware().render())
```
