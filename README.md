# RepGen — Automated Bug Reproduction

<div align="center">

<p align="center">
  <img src="https://img.shields.io/badge/Interface-CLI-4CAF50?style=flat-square" />
  <img src="https://img.shields.io/badge/Python-3.9%2B-3776AB?style=flat-square&logo=python&logoColor=white" />
  <img src="https://img.shields.io/github/actions/workflow/status/mehilshah/RepGen/ci.yml?branch=main&label=Build&style=flat-square&logo=github" />
  <img src="https://img.shields.io/badge/License-MIT-lightgrey?style=flat-square" />
</p>

[Features](#features) • [Quick Start](#quick-start) • [Usage](#usage) • [How it works](#how-it-works) • [Paper](https://arxiv.org/abs/2512.14990)

</div>

## Overview

**RepGen** is a command-line tool that uses Large Language Models to automatically
reproduce bugs in software libraries. Given a bug report and a repository, an
**exploration agent** navigates the codebase with tools (search, read, grep,
symbol lookup), then generates a Python reproduction script that is checked by a
**four-stage static verification loop** — *no generated code is ever executed*.

It is designed for Deep Learning libraries, where reproducing an issue (building a
Minimum Reproducible Example) is often the hardest first step of debugging.

## Features

- **Exploration-based retrieval.** Instead of a fixed pipeline, an agent explores
  the repo step by step (ReAct), gathering exactly the files, symbols, and
  signatures a reproduction needs.
- **Five LLM backends.** `openai`, `claude`, `gemini`, `openrouter`, and `ollama`
  (local, no API key) behind one interface — switch with a single flag.
- **Static verification, no execution.** Every generated script passes through
  four verifiers that produce structured, actionable feedback:
  1. **syntax** — `ast` parse
  2. **compilation** — `compile()` + focused `pylint` binding checks
  3. **pseudo-symbolic execution** — an AST abstract interpreter that resolves
     imports/signatures against what the agent discovered and checks that the
     reported failing API is actually exercised
  4. **LLM critique** — a structured judgement of whether the script reproduces
     the bug
- **Rich CLI.** Live exploration/verification views, a syntax-highlighted result,
  and a static `report.md` / `report.json` per run.
- **Dynamic, LLM-driven retrieval.** The agent reasons over an organized
  structural *repo map* (AST outlines of modules, classes, and signatures) plus a
  dependency-free BM25 index — semantic judgement is made by the model, not a
  static embedding ranker. No `torch`, no model downloads.

## Quick Start

```bash
# One lightweight install — no ML stack, no model downloads
pip install -e .
```

Run it with a local model (no API key required):

```bash
# Start Ollama separately: `ollama serve` and `ollama pull llama3.1`
repgen run \
  --bug-report https://github.com/owner/repo/issues/123 \
  --repo https://github.com/owner/repo.git \
  --backend ollama --model llama3.1
```

Or interactively — RepGen will prompt for anything you omit:

```bash
repgen run
```

## Usage

```bash
repgen run            # explore → generate → verify a reproduction
repgen backends       # show the 5 backends and which are configured
repgen config show    # view effective configuration
repgen config set backend claude
repgen version
```

Common `run` options:

| Flag | Description |
| --- | --- |
| `-b, --bug-report` | Path or URL to a bug report / GitHub issue |
| `-r, --repo` | Path or URL to the repository |
| `--backend` | `openai` · `claude` · `gemini` · `openrouter` · `ollama` |
| `--model` | Model name (defaults per backend) |
| `--commit` | Check out a specific commit before analysis |
| `--max-attempts` | Generation attempts per run (default 3) |
| `--max-explore-steps` | Exploration budget (default 12) |
| `-v, --verbose` | Stream every tool call and finding |
| `-y, --yes` | Non-interactive (fail if inputs are missing) |

### Configuration

Set API keys via environment variables:

```bash
export OPENAI_API_KEY="sk-..."
export ANTHROPIC_API_KEY="sk-ant-..."
export GEMINI_API_KEY="AIza..."
export OPENROUTER_API_KEY="sk-or-..."
# Ollama needs no key; override the host with OLLAMA_HOST if remote.
```

Persistent defaults live in `~/.config/repgen/config.toml` (`repgen config init`).
Resolution order is **CLI flags → config file → built-in defaults**.

### Docker

```bash
docker build -t repgen .
docker run --rm repgen backends
```

### Python API

```python
import repgen

script = repgen.reproduce(
    bug_report_source="https://github.com/owner/repo/issues/123",
    repo_source="https://github.com/owner/repo.git",
    backend="openai",
    model="gpt-4o",
)
print(script)
```

## How it works

```
bug report ──► refine ──► EXPLORE (agent + tools) ──► generate ──► VERIFY ──► script
                                │                                    │
                     RetrievedContext + SymbolIndex ────────────────┘
                          (feeds the symbolic verifier;
                     unresolved symbols trigger re-exploration)
```

Artifacts for every run are written to the output directory: the refined report,
the generated `reproduce.py`, and `report.md` / `report.json` summarizing the
exploration, the plan, and each verification attempt.

See the [documentation](docs/index.md) for the full architecture.

## Contributing

```bash
pip install -e ".[dev]"
pytest
```

Contributions are welcome — please open an issue or a PR.

## Issues

Open a GitHub issue or contact Mehil Shah at [shahmehil@dal.ca](mailto:shahmehil@dal.ca).

## License

MIT © [Mehil Shah](https://github.com/mehilshah)
