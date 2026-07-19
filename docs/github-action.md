# GitHub Action: reproduce bugs from issues

RepGen can run inside GitHub Actions and turn a labeled issue into a
reproduction script, posted straight back onto the issue as a comment.

```
issue labeled `needs-repro`  ─►  RepGen (Action)  ─►  comment: reproduction + report
```

## Adding it to your repo

RepGen is packaged as a reusable [composite action](../action.yml), so the
easiest install is a short workflow in **your** project (the repo whose issues
you want reproduced — not the RepGen repo):

```yaml
# .github/workflows/repgen.yml
name: RepGen
on:
  issues:
    types: [labeled]
jobs:
  reproduce:
    if: github.event.label.name == 'needs-repro'
    runs-on: ubuntu-latest
    permissions:
      contents: read      # checkout + time-travel to the issue date
      issues: write       # post the reproduction back as a comment
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }
      - uses: mehilshah/RepGen@v1
        with:
          backend: openai
        env:
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
```

Pass the LLM key that matches `backend` via `env:` on the `uses:` step
(`OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `GEMINI_API_KEY` /
`OPENROUTER_API_KEY`).

### Action inputs

| Input              | Default          | Description                                             |
| ------------------ | ---------------- | ------------------------------------------------------- |
| `backend`          | `openai`         | `openai` \| `anthropic` \| `gemini` \| `openrouter`.    |
| `model`            | backend default  | Pin a specific model ID.                                |
| `issue-url`        | triggering issue | Issue/bug-report URL to reproduce.                      |
| `execute`          | `false`          | Also run + verify (not just static checks).             |
| `reasoning-effort` | —                | `low` \| `medium` \| `high`.                            |
| `max-attempts`     | —                | Max generation attempts per run.                        |
| `output`           | `repgen_results` | Directory for RepGen results.                           |
| `comment`          | `true`           | Post the reproduction back as an issue comment.         |
| `repgen-ref`       | this action's ref | pip target for RepGen (e.g. `repgen-ai==0.2.0`).       |
| `github-token`     | `${{ github.token }}` | Token to read the issue and post the comment.      |
| `python-version`   | `3.12`           | Python version to run RepGen on.                        |

### Full example (every input)

A maximal workflow that sets every action input and lists all four backend keys.
Copy it and delete what you don't need — most repos only need `backend:` plus one
secret. Also available as
[`examples/github-action/repgen-full.yml`](../examples/github-action/repgen-full.yml).

```yaml
name: RepGen (full example)

on:
  issues:
    types: [labeled]

concurrency:
  group: repgen-${{ github.event.issue.number }}
  cancel-in-progress: true

jobs:
  reproduce:
    name: Reproduce labeled issue
    if: github.event.label.name == 'needs-repro'
    runs-on: ubuntu-latest
    permissions:
      contents: read      # checkout + time-travel the repo history
      issues: write       # post the reproduction back as a comment
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0   # all history, so RepGen can rewind to the bug date

      - uses: mehilshah/RepGen@v1
        with:
          # LLM backend
          backend: openai                  # openai | anthropic | gemini | openrouter
          model: gpt-4o                     # omit for the backend default
          # What to reproduce
          issue-url: ""                     # empty = the triggering issue
          # Depth / effort
          execute: "true"                   # true = run + verify; false = static checks only
          reasoning-effort: high            # low | medium | high
          max-attempts: "3"
          # Output / reporting
          output: repgen_results
          comment: "true"                   # post reproduction back on the issue
          # Plumbing
          repgen-ref: ""                    # e.g. 'repgen-ai==0.2.0'; empty = this action's ref
          python-version: "3.12"
          github-token: ${{ secrets.GITHUB_TOKEN }}
        env:
          # Provide the ONE key matching `backend:`. The rest are ignored.
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
          OPENROUTER_API_KEY: ${{ secrets.OPENROUTER_API_KEY }}
```

### Prefer to vendor the whole workflow?

If you'd rather own the full YAML instead of referencing `@v1`, copy the
standalone template [`examples/github-action/repgen-repro.yml`](../examples/github-action/repgen-repro.yml)
into your project's `.github/workflows/` directory.

## What it does

On every issue that receives the **`needs-repro`** label, the Action:

1. Checks out the repository (full history, so RepGen can *time-travel* the
   codebase back to the issue's creation date).
2. Installs RepGen.
3. Leaves an "on it" acknowledgement comment on the issue.
4. Runs `repgen run --yes --bug-report <issue-url> --repo .` and generates the
   reproduction.
5. Posts the generated `report.md` (reproduction script + static-verification
   summary) back as an issue comment, mirrors it into the job summary, and
   uploads the full `repgen_results/` directory as a build artifact.

It uses the built-in `GITHUB_TOKEN` to read the issue and post the comment — no
personal access token required.

## One-time setup

1. **Add your LLM key** as a repository secret
   (**Settings → Secrets and variables → Actions → New repository secret**):

   | Backend  | Secret name          |
   | -------- | -------------------- |
   | OpenAI   | `OPENAI_API_KEY`     |
   | Claude   | `ANTHROPIC_API_KEY`  |
   | Gemini   | `GEMINI_API_KEY`     |
   | OpenRouter | `OPENROUTER_API_KEY` |

2. **(Optional) Choose a backend/model** via the action's `with:` inputs —
   `backend:` and `model:` (see the [inputs table](#action-inputs)).

3. **Create the label.** Add a label named `needs-repro` to the repo, then apply
   it to any issue you want reproduced.

## Customizing

- **Change the trigger label:** edit the `if:` guard in your workflow —
  `if: github.event.label.name == 'needs-repro'`.
- **Also run + verify (not just static checks):** set `execute: true`.
  Execution is gated by RepGen's complexity planner; in non-interactive mode it
  runs *Quick* reproductions and skips heavier ones, so CI stays bounded.
- **Pin reasoning effort / attempts:** set the `reasoning-effort:` and
  `max-attempts:` inputs.
- **Pin the RepGen version:** set `repgen-ref:` (e.g. `repgen-ai==0.2.0`) so the
  action doesn't track its branch.

## Notes & limits

- The reproduction comment is truncated to stay under GitHub's ~65 kB comment
  limit; the untruncated `report.md` is always available as a workflow artifact.
- Private issues in other repos need a token with access; the default
  `GITHUB_TOKEN` only reads the repository the workflow runs in.
- LLM calls cost money — the Action runs once per `needs-repro` labeling, and
  `concurrency` cancels a superseded run for the same issue.
