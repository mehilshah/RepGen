# GitHub Action: reproduce bugs from issues

RepGen can run inside GitHub Actions and turn a labeled issue into a
reproduction script, posted straight back onto the issue as a comment.

```
issue labeled `needs-repro`  ─►  RepGen (Action)  ─►  comment: reproduction + report
```

The workflow file is [`.github/workflows/repgen-repro.yml`](../.github/workflows/repgen-repro.yml).

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

2. **(Optional) Choose a backend/model** via repository *variables*
   (same screen, "Variables" tab):

   - `REPGEN_BACKEND` — defaults to `openai`.
   - `REPGEN_MODEL` — pin a specific model ID (otherwise the backend default).

3. **Create the label.** Add a label named `needs-repro` to the repo, then apply
   it to any issue you want reproduced.

## Customizing

- **Change the trigger label:** edit the `if:` guard in the job —
  `if: github.event.label.name == 'needs-repro'`.
- **Also run + verify (not just static checks):** remove the `--no-execute`
  flag from the `Run RepGen` step. Execution is gated by RepGen's complexity
  planner; in non-interactive mode it runs *Quick* reproductions and skips
  heavier ones, so CI stays bounded.
- **Pin reasoning effort / attempts:** add `--reasoning-effort`, `--max-attempts`,
  or `--max-explore-steps` to the `repgen run` command.

## Notes & limits

- The reproduction comment is truncated to stay under GitHub's ~65 kB comment
  limit; the untruncated `report.md` is always available as a workflow artifact.
- Private issues in other repos need a token with access; the default
  `GITHUB_TOKEN` only reads the repository the workflow runs in.
- LLM calls cost money — the Action runs once per `needs-repro` labeling, and
  `concurrency` cancels a superseded run for the same issue.
