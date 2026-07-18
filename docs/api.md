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
)
print(script)
```

`reproduce` returns the generated script as a string and raises `RuntimeError`
if no script could be produced.

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

## Backends

```python
from repgen.backends import get_backend, list_backends

client = get_backend("claude", model="claude-sonnet-4-5")
print(client.is_configured())
response = client.generate("Say hi.")
print(response.text)
```
