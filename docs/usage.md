# Usage

RepGen is a subcommand-based CLI.

```bash
repgen run            # explore → generate → verify → execute a reproduction
repgen backends       # list backends and which are configured
repgen models         # list suggested state-of-the-art models per backend
repgen frameworks     # list supported target frameworks
repgen new PATH       # scaffold a new local project for a framework
repgen open PATH      # inspect an existing local project
repgen config ...     # manage persistent defaults
repgen version
```

## Running a reproduction

Interactive — RepGen prompts for anything you omit:

```bash
repgen run
```

Non-interactive:

```bash
repgen run \
  --bug-report https://github.com/owner/repo/issues/123 \
  --repo https://github.com/owner/repo.git \
  --backend ollama --model llama3.1 \
  --yes
```

### `run` options

| Flag | Description |
| --- | --- |
| `-b, --bug-report` | Path or URL to a bug report / GitHub issue |
| `-r, --repo` | Path or URL to the repository |
| `--backend` | `openai` · `claude` · `gemini` · `openrouter` · `ollama` |
| `--model` | Model name (defaults per backend) |
| `--commit` | Check out a specific commit before analysis |
| `-o, --output` | Output directory (default `./repgen_results`) |
| `--max-attempts` | Generation attempts per run (default 3) |
| `--max-explore-steps` | Exploration budget (default 12) |
| `-f, --framework` | Target framework: `plain` · `fastapi` · `flask` · `django` · `streamlit` |
| `--execute / --no-execute` | Run the generated script in an isolated venv (default from config) |
| `--max-exec-retries` | Refine/retry attempts after a failed execution (default 2) |
| `-v, --verbose` | Stream every tool call, command, and finding |
| `-y, --yes` | Non-interactive; fail if inputs are missing |

## Execution engine

By default RepGen does more than write a script — it **runs** it and checks
whether the bug actually reproduces. After generation it:

1. **Detects dependencies** from the script's imports and updates
   `requirements.txt`.
2. **Plans** the run with an LLM + your hardware (CPU/RAM/GPU/disk), classifying
   it as **Quick** (~5–10 min), **Medium** (~10–40 min), or **Large** (40 min+).
3. **Gates** on that classification:
    - *Quick* runs execute automatically.
    - *Medium* runs show the estimate and ask whether to proceed.
    - *Large* runs let you **execute**, **prepare the environment only**, or
      **skip**.
4. **Prepares** an isolated `venv`, installs dependencies (streamed), and
   **executes** the script, streaming stdout/stderr live with structured
   tracebacks.
5. **Verifies** reproduction by comparing the real output against the bug report
   (LLM + signature/semantic matching), reporting a verdict, confidence, and
   matching evidence.
6. **Refines & retries** up to `--max-exec-retries` times when execution fails
   for incidental reasons, with the LLM analyzing the logs.

Disable execution (static verification only, the original behaviour) with
`--no-execute` or `repgen config set execute false`. In non-interactive mode
(`--yes`) only *Quick* runs execute; heavier runs are skipped.

## Local projects & frameworks

Open an existing local project or scaffold a new one, then point `run` at it:

```bash
repgen new ./myapi --framework fastapi     # scaffold a FastAPI project
repgen open ./existing-project             # inspect a local project
repgen run --repo ./myapi --framework fastapi -b claude
```

The chosen framework seeds base dependencies, the execution command, and the
project's test configuration.

## Backends & keys

```bash
export OPENAI_API_KEY="sk-..."
export ANTHROPIC_API_KEY="sk-ant-..."
export GEMINI_API_KEY="AIza..."
export OPENROUTER_API_KEY="sk-or-..."
# Ollama is keyless; set OLLAMA_HOST to point at a remote server.
```

`repgen backends` shows each provider, its default model, and whether it is
configured.

## Configuration file

Persistent defaults live in `~/.config/repgen/config.toml` (override the location
with `$REPGEN_CONFIG`).

```bash
repgen config init                       # write defaults
repgen config show                       # view effective config
repgen config set backend claude         # change a value
repgen config set execute false          # static-only (disable execution)
repgen config set framework fastapi      # default target framework
repgen config set max_exec_retries 3     # refine/retry budget
repgen config path                       # print the file path
```

Execution-related keys: `execute`, `framework`, `max_exec_retries`,
`quick_timeout_s`, `medium_timeout_s`, `large_timeout_s`.

Resolution order: **CLI flags → config file → built-in defaults**.

## Output

Each run writes a timestamped directory under the output folder:

```text
repgen_results/
└── RepGen_Run_<timestamp>/
    ├── input_bug_report.txt   # fetched bug report
    ├── refined_report.txt     # structured analysis
    ├── reproduce.py           # generated (and refined) reproduction script
    ├── requirements.txt       # auto-detected dependencies (when execution runs)
    ├── .venv/                 # isolated environment used for execution
    ├── run_commands.sh        # setup/install/run commands (prepare-only runs)
    ├── report.md              # human-readable run report
    └── report.json            # machine-readable run report
```
