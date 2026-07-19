"""Rich visualizations for the CLI and static run-report writers."""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Dict

from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from .console import console

# Symbols used in the per-attempt feedback view.
_MARK = {True: "[green]✓[/green]", False: "[red]✗[/red]"}

_STAGE_STYLE = {
    "setup": "cyan",
    "refine": "magenta",
    "explore": "blue",
    "generate": "green",
}


class RunReporter:
    """Consumes the service progress events and renders them live."""

    def __init__(self, verbose: bool = False):
        self.verbose = verbose

    def __call__(self, event: str, data: Dict[str, Any]) -> None:
        try:
            self._handle(event, data)
        except Exception:  # noqa: BLE001 - never let reporting crash a run
            pass

    def _handle(self, event: str, data: Dict[str, Any]) -> None:
        if event in _STAGE_STYLE:
            style = _STAGE_STYLE[event]
            console.print(f"[{style}][{event.upper()}][/] {data.get('message', '')}")

        elif event == "refine_done":
            refined = str(data.get("refined", "")).strip()
            if not refined:
                console.print("  [dim]bug report refined[/dim]")
            elif self.verbose:
                console.print(
                    Panel(
                        refined,
                        title="[bold]Refined bug report[/bold]",
                        border_style="magenta",
                        expand=False,
                    )
                )
            else:
                # Collapsed by default: keep the log concise. The full refined
                # report is saved to ``refined_report.txt`` in the run directory
                # (and shown inline with -v).
                lines = refined.count("\n") + 1
                console.print(
                    f"  [magenta]▸ refined bug report[/magenta] "
                    f"[dim]{lines} lines · saved to refined_report.txt · "
                    f"-v to show[/dim]"
                )

        elif event == "explore.repo_map":
            modules = str(data.get("overview", "")).count("\n") + 1
            console.print(
                f"  [blue]loaded repo map[/blue] [dim](~{modules} lines)[/dim]"
            )

        elif event == "explore.action":
            tool = data.get("tool", "?")
            args = data.get("args", {})
            thought = data.get("thought", "")
            arg_str = ", ".join(f"{k}={v!r}" for k, v in list(args.items())[:2])
            line = f"  [blue]→[/blue] step {data.get('step')}: [bold]{tool}[/bold]({arg_str})"
            if thought and self.verbose:
                line += f"  [dim]{thought[:60]}[/dim]"
            console.print(line)

        elif event == "explore.observation" and self.verbose:
            obs = str(data.get("observation", "")).splitlines()
            preview = obs[0][:80] if obs else ""
            console.print(f"    [dim]{preview}[/dim]")

        elif event == "explore.finish":
            console.print(
                f"  [blue]■[/blue] finished: [dim]{data.get('rationale', '')[:80]}[/dim]"
            )

        elif event == "explore_done":
            files = data.get("files", [])
            symbols = data.get("symbols", [])
            body = "\n".join(f"  • {f}" for f in files) or "  [dim](none)[/dim]"
            if symbols:
                shown = ", ".join(symbols[:12])
                more = f" (+{len(symbols) - 12} more)" if len(symbols) > 12 else ""
                body += f"\n\n[dim]Resolved symbols:[/dim] {shown}{more}"
            console.print(
                Panel(
                    body,
                    title=f"[bold]Explored context — {len(files)} key file(s)[/bold]",
                    border_style="blue",
                    expand=False,
                )
            )

        elif event == "generate.failure_signature":
            sig = data.get("signature")
            if sig and getattr(sig, "trigger_apis", None):
                console.print(
                    f"  [dim]expected failure: {sig.exception_type or '?'} "
                    f"via {', '.join(sig.trigger_apis[:3])}[/dim]"
                )

        elif event == "generate.plan" and self.verbose:
            console.print(
                Panel(data.get("plan", ""), title="Plan", border_style="green")
            )

        elif event == "generate.attempt_start":
            console.print(
                f"  [green]attempt {data.get('attempt')}/{data.get('total')}[/green]"
            )

        elif event == "generate.attempt_verified":
            marks = []
            for fb in data.get("feedbacks", []):
                marks.append(f"{fb.stage} {_MARK[fb.passed]}")
            console.print("    " + " · ".join(marks))
            if not data.get("passed"):
                for fb in data.get("feedbacks", []):
                    if not fb.passed:
                        for finding in fb.findings[:3]:
                            console.print(f"      [yellow]- {finding.message}[/yellow]")

        elif event == "generate.reexplore":
            console.print("  [yellow]↻ re-exploring for unresolved symbols...[/yellow]")

        elif event == "error":
            console.print(f"[error]Error: {data.get('message')}[/error]")

    # -- final summary ----------------------------------------------------
    def summary(self, result: Dict[str, Any]) -> None:
        console.print()
        if result["success"]:
            console.print(
                Panel(
                    "[bold green]Reproduction verified (static checks passed)[/bold green]",
                    border_style="green",
                )
            )
        else:
            console.print(
                Panel(
                    f"[yellow]{result.get('error', 'Did not fully verify.')}[/yellow]",
                    title="[bold yellow]Incomplete[/bold yellow]",
                    border_style="yellow",
                )
            )

        for file_info in result.get("files", []):
            path = file_info["path"]
            console.print(
                Panel(
                    Syntax(
                        file_info["content"],
                        "python",
                        theme="monokai",
                        line_numbers=True,
                    ),
                    title=f"[cyan]{Path(path).name}[/cyan]",
                    border_style="cyan",
                )
            )

        if result.get("run_dir"):
            console.print(f"\n[bold]Artifacts:[/bold] {result['run_dir']}")
        if result.get("report"):
            console.print(f"[bold]Report:[/bold] {result['report']}")
        for file_info in result.get("files", []):
            console.print(f"[bold]Run:[/bold] python {file_info['path']}")


# ==========================================================================
# Static report writers
# ==========================================================================


def _serialize(obj: Any) -> Any:
    if is_dataclass(obj) and not isinstance(obj, type):
        return {k: _serialize(v) for k, v in asdict(obj).items()}
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_serialize(v) for v in obj]
    return obj


def write_run_report(
    run_dir: Path,
    *,
    backend: str,
    model: str,
    refined_report: str,
    context,
    generation,
    timings: Dict[str, float],
) -> Path:
    """Write ``report.json`` and ``report.md`` to the run directory."""
    attempts = []
    for att in generation.attempts:
        attempts.append(
            {
                "index": att.index,
                "passed": att.result.passed,
                "feedback": [
                    {
                        "stage": fb.stage,
                        "passed": fb.passed,
                        "findings": [f.message for f in fb.findings],
                    }
                    for fb in att.result.feedbacks
                ],
            }
        )

    data = {
        "backend": backend,
        "model": model,
        "success": generation.success,
        "timings_seconds": {k: round(v, 2) for k, v in timings.items()},
        "key_files": context.key_files,
        "symbols_discovered": list(context.symbol_index.all_symbols().keys()),
        "failure_signature": _serialize(generation.failure_signature),
        "plan": generation.plan,
        "attempts": attempts,
        "code": generation.code,
    }
    (run_dir / "report.json").write_text(json.dumps(data, indent=2, default=str))

    md = _render_markdown(data, refined_report)
    report_md = run_dir / "report.md"
    report_md.write_text(md)
    return report_md


def _render_markdown(data: Dict[str, Any], refined_report: str) -> str:
    lines = [
        "# RepGen Reproduction Report",
        "",
        f"- **Backend:** {data['backend']} ({data['model']})",
        f"- **Verified:** {'yes' if data['success'] else 'no'}",
        f"- **Timings (s):** {data['timings_seconds']}",
        "",
        "## Refined bug report",
        "",
        "```",
        refined_report.strip(),
        "```",
        "",
        "## Explored context",
        "",
        "Key files: " + (", ".join(data["key_files"]) or "—"),
        "",
        "Symbols discovered: " + (", ".join(data["symbols_discovered"][:30]) or "—"),
        "",
        "## Plan",
        "",
        data["plan"] or "—",
        "",
        "## Verification attempts",
        "",
    ]
    for att in data["attempts"]:
        status = "passed" if att["passed"] else "failed"
        lines.append(f"### Attempt {att['index']} — {status}")
        for fb in att["feedback"]:
            mark = "✓" if fb["passed"] else "✗"
            lines.append(f"- {mark} **{fb['stage']}**")
            for finding in fb["findings"]:
                lines.append(f"    - {finding}")
        lines.append("")

    lines += ["## Generated script", "", "```python", data["code"] or "", "```", ""]
    return "\n".join(lines)


def build_summary_table(title: str) -> Table:
    table = Table(title=title, show_header=True, header_style="bold magenta")
    return table
