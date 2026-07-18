# Testing RepGen

## Automated tests

```bash
pip install -e ".[dev]"
pytest
```

The suite covers the backend registry, configuration, repository tools, the
exploration loop, and all four static verifiers — no network access required.

## Manual CLI checks (no API key)

```bash
repgen version
repgen backends           # ollama shows as configured (keyless)
repgen config show
```

## End-to-end reproduction

Using a local model via Ollama (no API key):

```bash
# In another terminal: `ollama serve` then `ollama pull llama3.1`
repgen run \
  -b https://github.com/owner/repo/issues/123 \
  -r https://github.com/owner/repo.git \
  --backend ollama --model llama3.1 --verbose
```

Or with a hosted backend:

```bash
export OPENAI_API_KEY="sk-..."
repgen run -b ./bug.txt -r ./path/to/repo --backend openai --yes
```

Confirm that:

1. exploration tool calls stream in the live view (`--verbose`),
2. each attempt reports `syntax · compilation · symbolic · critique` status,
3. `reproduce.py`, `report.md`, and `report.json` are written to the run
   directory printed at the end.

## Docker

```bash
docker build -t repgen .
docker run --rm repgen backends
```
