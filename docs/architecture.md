# Architecture

RepGen turns a bug report and a repository into a verified reproduction script
through four stages.

```
bug report ──► refine ──► EXPLORE (agent + tools) ──► generate ──► VERIFY ──► script
                                │                                    │
                     RetrievedContext + SymbolIndex ─────────────────┘
                          (feeds the symbolic verifier;
                     unresolved symbols trigger re-exploration)
```

## 1. Refinement

The raw bug report is restructured by the LLM into a title, symptoms, expected
behaviour, and reproduction steps (`repgen/prompts.py`).

## 2. Exploration (dynamic, LLM-driven retrieval)

Instead of a fixed pipeline or static embedding similarity, RepGen builds an
**organized structural map** of the repository and lets the LLM reason over it to
decide *where to look*. The map (`repgen/agent/repomap.py`) is an AST-derived
outline of every module — classes, methods, and function signatures with docstring
lines — and is seeded into the agent's context at the start of exploration. This is
what makes retrieval *dynamic*: relevance is judged by the model as it explores,
not precomputed by a similarity index.

An **exploration agent** (`repgen/agent/explorer.py`) then runs a text-ReAct loop.
Each step, the model emits a single JSON action and RepGen executes the
corresponding tool (`repgen/agent/tools.py`):

| Tool | Purpose |
| --- | --- |
| `repo_map` | Show the structural map (optionally scoped to a path prefix) to reason about where to look |
| `search_code` | Dependency-free BM25 keyword search over code units (functions/classes) |
| `list_dir` / `read_file` | Navigate and read files (line ranges supported) |
| `grep` | Regex search across the repo |
| `find_definition` | Locate a function/class definition via AST |
| `find_training_loops` | List files containing ML training loops (AST heuristic) |
| `finish` | End exploration with a rationale and key files |

Retrieval is intentionally **dependency-light**: the repo map and BM25 index are
pure Python (no `torch`, embeddings, or model downloads), so semantic reasoning is
delegated to the LLM rather than a static neural ranker.

Exploration produces two artifacts (`repgen/agent/context.py`):

- **`RetrievedContext`** — the ordered files/snippets the agent chose, rendered
  into the generation prompt.
- **`SymbolIndex`** — a `module → symbol → signature` map built by AST-parsing
  every file read. This is the key input to the pseudo-symbolic verifier.

The text-ReAct protocol (plain JSON actions, not native tool-calling) is used so
that every backend — including local Ollama models — works uniformly.

## 3. Generation

`repgen/agent/generator.py` produces a step-by-step plan, then a reproduction
script. Failed verification feeds structured feedback into the next attempt; when
the symbolic verifier reports an *unresolved symbol*, the generator re-invokes
exploration to gather the missing context before retrying.

## 4. Static verification (no execution)

The generated script never runs. Instead, `repgen/agent/feedback.py` chains four
verifiers (`repgen/agent/verifiers/`), each returning structured, actionable
findings:

1. **Syntax** — `ast.parse`.
2. **Compilation** — `compile()` to bytecode plus a focused `pylint` pass for
   binding errors (`undefined-variable`, `used-before-assignment`).
3. **Pseudo-symbolic execution** — an AST abstract interpreter that:
   - resolves imports/attributes against the `SymbolIndex` (or a known
     third-party allowlist);
   - checks call signatures (arity, unknown keywords, missing required args)
     against retrieved definitions;
   - verifies the reported failing API is actually invoked and an observation
     point (assert/print/try-except) is present.
4. **LLM critique** — a structured judgement of whether the script reproduces the
   reported bug.

Static verification always runs as a **pre-execution gate**: it catches broken
scripts cheaply before any environment is built.

## 5. Execution (optional, opt-out with `--no-execute`)

Once a script passes static verification, the execution engine
(`repgen/execution/`) runs it for real and checks whether the bug reproduces.

```
script ──► detect deps ──► PLAN (LLM + hardware) ──► gate ──► venv ──► install
             (AST)          Quick / Medium / Large           (isolated)   │
                                                                          ▼
   verdict ◄── VERIFY (LLM + signature) ◄── RUN (stream stdout/stderr) ◄──┘
     │                                                                    ▲
     └──► refine (LLM analyzes logs) ──► retry ────────────────────────────
```

| Component | Responsibility |
| --- | --- |
| `hardware.py` | Detect CPU/RAM/GPU/disk (stdlib, optional `psutil`) |
| `dependencies.py` | AST import scan → PyPI names, update `requirements.txt` |
| `environment.py` | Create a per-run `venv`, stream `pip install` |
| `planner.py` | LLM + hardware → complexity (Quick/Medium/Large) + estimate |
| `runner.py` | Stream stdout/stderr, enforce timeout, parse tracebacks |
| `reproduction.py` | Compare output vs report (LLM + signature/semantic) → verdict |
| `frameworks.py` | Per-framework deps, run command, scaffold, test config |
| `pipeline.py` | Orchestrate plan → prepare → run → verify → refine/retry |

Complexity gating decides whether a run executes automatically (*Quick*), asks
for confirmation (*Medium*), or offers execute/prepare-only/skip (*Large*). A
reproduction that raises the *expected* exception is treated as success even
though it exits non-zero, so a valid repro is never "refined away". The Rich UI
in `repgen/ui/` renders streaming output, dependency status, collapsible logs,
tracebacks, the reproduction verdict, and a final summary.

Execution is **opt-out** (`--no-execute` / `execute = false`); the static
pipeline above is unchanged and remains the fallback.

## Artifacts

Every run writes `input_bug_report.txt`, `refined_report.txt`, `reproduce.py`,
and `report.md` / `report.json` (exploration summary, plan, and per-attempt
verification results) to the output directory. When execution runs it also
writes `requirements.txt`, the per-run `.venv/`, and (for prepare-only runs)
`run_commands.sh`.
