"""Rich rendering of execution-pipeline progress events.

:class:`ExecutionReporter` is a ``progress_callback`` for
:class:`repgen.execution.pipeline.ExecutionPipeline`. It mirrors the event
protocol the pipeline emits and renders each stage with a clean, milestone-first
layout:

* stage banners and milestone lines (deps, plan, decision, verdict),
* the exact venv/pip/run commands (command visibility),
* structured error/traceback panels and a bug-reproduction verdict,
* a final execution summary table.

Noisy detail — pip/venv chatter and the program's own stdout/stderr — is handled
by verbosity:

* **silent (default):** the detail is written to ``execution.log`` in the run
  directory and kept out of the terminal; a one-line pointer is shown instead.
* **verbose (``-v``):** the full detail is streamed inline as it happens (and
  still saved to the log file).

It never raises: rendering failures are swallowed so a display bug can't crash a
run (matching :class:`repgen.reporting.RunReporter`).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, TextIO

from rich.panel import Panel
from rich.prompt import Prompt
from rich.rule import Rule
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from ..console import console

_LOG_FILENAME = "execution.log"


class ExecutionReporter:
    """Renders execution-pipeline events; usable as a progress callback."""

    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self._started = False
        self._log_file: Optional[TextIO] = None
        self._log_path: Optional[Path] = None
        self._log_lines = 0

    # progress_callback signature: (event, data)
    def __call__(self, event: str, data: Dict[str, Any]) -> None:
        try:
            self._handle(event, data)
        except Exception:  # noqa: BLE001 - never let the UI crash a run
            pass

    def _banner(self) -> None:
        if self._started:
            return
        self._started = True
        console.print(Rule("[bold cyan]Execution[/bold cyan]", style="cyan"))

    # -- detailed-log plumbing -------------------------------------------
    def _open_log(self, run_dir: str) -> None:
        """Open the detailed run log in the run directory (once)."""
        if self._log_file is not None or not run_dir:
            return
        try:
            path = Path(run_dir) / _LOG_FILENAME
            self._log_file = open(path, "w", encoding="utf-8")
            self._log_path = path
            if not self.verbose:
                console.print(
                    f"  [dim]detailed output → {path} "
                    f"(use -v to show it inline)[/dim]"
                )
        except Exception:  # noqa: BLE001 - logging is best-effort
            self._log_file = None
            self._log_path = None

    def _detail(self, line: str, stream: str = "stdout") -> None:
        """Record one detail line: to the log file always, inline if verbose."""
        if self._log_file is not None:
            try:
                self._log_file.write(line + "\n")
                self._log_file.flush()
                self._log_lines += 1
            except Exception:  # noqa: BLE001
                pass
        if self.verbose:
            style = "yellow" if stream == "stderr" else "white"
            console.print(Text("    " + line, style=style))

    def _close_log(self) -> None:
        if self._log_file is not None:
            try:
                self._log_file.close()
            except Exception:  # noqa: BLE001
                pass
            self._log_file = None

    def _handle(self, event: str, data: Dict[str, Any]) -> None:  # noqa: C901
        if event == "hardware":
            self._banner()
            info = data.get("info")
            if info is not None and self.verbose:
                console.print(
                    Panel(
                        info.render(),
                        title="[cyan]Detected hardware[/cyan]",
                        border_style="cyan",
                        expand=False,
                    )
                )

        elif event == "dependencies":
            report = data.get("report")
            if report is not None:
                console.print(f"  [cyan]deps[/cyan] {report.render()}")

        elif event == "plan":
            self._render_plan(data.get("plan"))

        elif event == "decision":
            decision = data.get("decision")
            style = {"execute": "green", "prepare_only": "yellow", "skip": "dim"}.get(
                decision, "white"
            )
            console.print(f"  [{style}]decision:[/] {decision}")

        elif event == "env_prepare_start":
            self._open_log(data.get("run_dir", ""))
            console.print("  [cyan]▶ preparing virtual environment...[/cyan]")

        elif event == "env_line":
            self._detail(data.get("line", ""), data.get("stream", "stdout"))

        elif event == "repo_requirements_start":
            console.print(
                f"  [cyan]▶ installing repo requirements[/cyan] "
                f"[dim]{data.get('file', '')}[/dim]"
            )

        elif event == "repo_requirements_done":
            result = data.get("result")
            if result is not None:
                mark = "[green]✓[/green]" if result.success else "[yellow]·[/yellow]"
                console.print(f"  {mark} repo requirements installed")

        elif event == "project_install_start":
            kind = "editable " if data.get("editable") else ""
            console.print(
                f"  [cyan]▶ installing library under test ({kind}source)[/cyan] "
                f"[dim]{data.get('path', '')}[/dim]"
            )

        elif event == "project_install_done":
            result = data.get("result")
            if result is not None:
                mark = "[green]✓[/green]" if result.success else "[yellow]·[/yellow]"
                console.print(f"  {mark} library under test installed")

        elif event == "project_on_path":
            console.print(
                f"  [cyan]library under test on PYTHONPATH[/cyan] "
                f"[dim]{data.get('path', '')}[/dim]"
            )

        elif event == "requirements_updated":
            added = data.get("added") or []
            if added:
                console.print(
                    f"  [green]requirements.txt[/green] +{len(added)}: "
                    f"[dim]{', '.join(added)}[/dim]"
                )

        elif event == "install_start":
            reqs = data.get("requirements") or []
            console.print(
                f"  [cyan]▶ installing {len(reqs)} package(s):[/cyan] "
                f"[dim]{', '.join(reqs)}[/dim]"
            )

        elif event == "install_line":
            self._detail(data.get("line", ""), data.get("stream", "stdout"))

        elif event == "install_done":
            result = data.get("result")
            if result is not None:
                mark = "[green]✓[/green]" if result.success else "[red]✗[/red]"
                console.print(f"  {mark} dependencies installed")
                if not result.success:
                    self._point_to_log("install output")

        elif event == "install_failed":
            console.print(f"  [red]✗ {data.get('message', 'install failed')}[/red]")

        elif event == "prepare_only":
            console.print(
                Panel(
                    "Environment prepared. Execution skipped by your choice.\n"
                    "See [bold]run_commands.sh[/bold] in the run directory to run it "
                    "yourself.",
                    title="[yellow]Prepare-only[/yellow]",
                    border_style="yellow",
                )
            )

        elif event == "exec_start":
            attempt = data.get("attempt", 1)
            total = data.get("total", 1)
            cmd = " ".join(data.get("command", []))
            console.print(
                f"\n  [bold green]▶ run[/bold green] "
                f"[dim](attempt {attempt}/{total}, timeout {data.get('timeout')}s)[/dim]"
            )
            console.print(f"    [code]$ {cmd}[/code]")

        elif event == "exec_line":
            self._detail(data.get("line", ""), data.get("stream", "stdout"))

        elif event == "exec_done":
            result = data.get("result")
            if result is not None:
                self._render_exec_done(result)

        elif event == "verdict":
            self._render_verdict(data.get("verdict"))

        elif event == "refine":
            console.print(
                f"  [magenta]↻ refining[/magenta] "
                f"[dim]{data.get('root_cause', '')[:80]}[/dim]"
            )

        elif event == "refine_noop":
            console.print("  [dim]refinement produced no change; stopping.[/dim]")

        elif event == "retries_exhausted":
            console.print("  [yellow]retries exhausted.[/yellow]")

        elif event == "env_error":
            console.print(f"  [red]✗ environment error: {data.get('message')}[/red]")

    # -- sub-renderers ----------------------------------------------------
    def _point_to_log(self, what: str) -> None:
        """In silent mode, point at the log file when something needs a look."""
        if not self.verbose and self._log_path is not None:
            console.print(f"    [dim]see {what} in {self._log_path}[/dim]")

    def _render_plan(self, plan) -> None:
        if plan is None:
            return
        color = {"Quick": "green", "Medium": "yellow", "Large": "red"}.get(
            plan.complexity.label, "white"
        )
        console.print(
            Panel(
                plan.render(),
                title=f"[{color}]Execution plan — {plan.complexity.label}[/{color}]",
                border_style=color,
                expand=False,
            )
        )

    def _render_exec_done(self, result) -> None:
        if result.success:
            console.print(f"  [green]✓ {result.summary()}[/green]")
        elif result.timed_out:
            console.print(f"  [red]✗ {result.summary()}[/red]")
        else:
            console.print(f"  [yellow]· {result.summary()}[/yellow]")
        if result.traceback and result.raised:
            console.print(
                Panel(
                    Syntax(
                        result.traceback.strip(),
                        "pytb",
                        theme="monokai",
                        word_wrap=True,
                    ),
                    title="[red]Traceback[/red]",
                    border_style="red",
                    expand=False,
                )
            )

    def _render_verdict(self, verdict) -> None:
        if verdict is None:
            return
        if verdict.reproduced:
            title = "[bold green]Bug reproduced[/bold green]"
            style = "green"
        else:
            title = "[bold yellow]Not reproduced[/bold yellow]"
            style = "yellow"
        body = [f"Confidence: {verdict.confidence:.0%}"]
        if verdict.key_error:
            body.append(f"Key error: {verdict.key_error}")
        if verdict.explanation:
            body.append(verdict.explanation)
        if verdict.matching_evidence:
            body.append("\nMatching evidence:")
            body += [f"  ✓ {e}" for e in verdict.matching_evidence]
        if not verdict.reproduced and verdict.debugging_insights:
            body.append("\nDebugging insights:")
            body += [f"  → {h}" for h in verdict.debugging_insights]
        console.print(
            Panel("\n".join(body), title=title, border_style=style, expand=False)
        )

    # -- final summary ----------------------------------------------------
    def summary(self, outcome) -> None:
        """Render the final execution summary table."""
        self._close_log()
        try:
            self._summary(outcome)
        except Exception:  # noqa: BLE001
            pass

    def _summary(self, outcome) -> None:
        if outcome is None:
            return
        table = Table(
            title="Execution summary",
            header_style="bold magenta",
            show_header=True,
            expand=False,
        )
        table.add_column("Field", style="cyan")
        table.add_column("Value")
        table.add_row("Executed", "yes" if outcome.executed else "no")
        table.add_row(
            "Decision", str(getattr(outcome.decision, "value", outcome.decision))
        )
        if outcome.plan:
            table.add_row("Complexity", outcome.plan.complexity.label)
            table.add_row("Est. runtime", f"~{outcome.plan.estimated_minutes:.0f} min")
        table.add_row("Attempts", str(len(outcome.attempts)))
        last = outcome.last_attempt
        if last is not None:
            table.add_row("Final run", last.result.summary())
        if outcome.attempts:
            table.add_row("Reproduced", "yes" if outcome.reproduced else "no")
        if outcome.error:
            table.add_row("Error", outcome.error)
        if self._log_path is not None and self._log_lines:
            table.add_row("Detailed log", str(self._log_path))
        console.print(table)


def interactive_confirm(plan, hardware):
    """Interactive confirm callback for the Medium/Large complexity gates.

    Returns an :class:`~repgen.execution.pipeline.ExecutionDecision`.
    """
    from ..execution.pipeline import ExecutionDecision
    from ..execution.planner import Complexity

    color = {"Quick": "green", "Medium": "yellow", "Large": "red"}.get(
        plan.complexity.label, "white"
    )
    console.print(
        Panel(
            plan.render() + "\n\n[dim]Host:[/dim]\n" + hardware.render(),
            title=f"[{color}]This run is estimated {plan.complexity.label}[/{color}]",
            border_style=color,
            expand=False,
        )
    )

    if plan.complexity is Complexity.MEDIUM:
        choice = Prompt.ask(
            "Proceed with execution?",
            choices=["yes", "no"],
            default="yes",
        )
        return ExecutionDecision.EXECUTE if choice == "yes" else ExecutionDecision.SKIP

    # Large (or anything heavier): offer the three-way choice.
    choice = Prompt.ask(
        "Choose: [e]xecute, [p]repare environment only, or [s]kip",
        choices=["e", "p", "s"],
        default="p",
    )
    return {
        "e": ExecutionDecision.EXECUTE,
        "p": ExecutionDecision.PREPARE_ONLY,
        "s": ExecutionDecision.SKIP,
    }[choice]
