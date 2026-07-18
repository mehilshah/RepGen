# RepGen

**Exploration-based automated bug reproduction with Large Language Models.**

[Paper](https://arxiv.org/abs/2512.14990)

---

## Overview

RepGen is a command-line tool that automatically reproduces bugs in software
libraries. Given a bug report and a repository, an **exploration agent** navigates
the codebase with tools, then generates a Python reproduction script that is
checked by a **four-stage static verification loop**. No generated code is ever
executed.

It is designed for Deep Learning libraries, where building a Minimum Reproducible
Example is the hardest first step of debugging.

## Features

- **Dynamic, LLM-driven retrieval** — a ReAct agent reasons over an organized
  structural *repo map* and uses `repo_map`, `search_code` (BM25), `read_file`,
  `grep`, `find_definition`, and `find_training_loops` to gather exactly the
  context a reproduction needs.
- **Five LLM backends** — `openai`, `claude`, `gemini`, `openrouter`, and `ollama`
  (local, keyless) behind one interface.
- **Static verification (no execution)** — syntax, compilation (`compile()` +
  `pylint`), pseudo-symbolic execution, and structured LLM critique.
- **Rich CLI** with live views and per-run `report.md` / `report.json` artifacts.
- **Dependency-light** — retrieval is a pure-Python repo map + BM25, so there is
  no `torch` or embedding-model install.

## Where to next

- [Installation](installation.md)
- [Usage](usage.md)
- [Architecture](architecture.md)
- [Python API](api.md)
