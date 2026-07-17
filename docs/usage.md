# Usage

RepGen is a subcommand-based CLI.

```bash
repgen run            # explore → generate → verify a reproduction
repgen backends       # list backends and which are configured
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
| `-v, --verbose` | Stream every tool call and finding |
| `-y, --yes` | Non-interactive; fail if inputs are missing |

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
repgen config init                    # write defaults
repgen config show                    # view effective config
repgen config set backend claude      # change a value
repgen config path                    # print the file path
```

Resolution order: **CLI flags → config file → built-in defaults**.

## Output

Each run writes a timestamped directory under the output folder:

```text
repgen_results/
└── RepGen_Run_<timestamp>/
    ├── input_bug_report.txt   # fetched bug report
    ├── refined_report.txt     # structured analysis
    ├── reproduce.py           # generated reproduction script
    ├── report.md              # human-readable run report
    └── report.json            # machine-readable run report
```
