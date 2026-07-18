"""RepGen command-line interface (Typer)."""

from __future__ import annotations

import os
import sys
from typing import Optional

import typer
from rich.panel import Panel
from rich.prompt import IntPrompt, Prompt
from rich.table import Table

from . import __version__
from .backends import BACKEND_NAMES, get_backend, list_backends
from .backends.models import model_specs
from .config import RepGenConfig, config_path
from .console import configure_logging, console
from .core import RepGenService
from .execution.frameworks import FRAMEWORK_NAMES, get_framework, list_frameworks
from .execution.pipeline import ExecutionSettings
from .reporting import RunReporter
from .ui import ExecutionReporter, interactive_confirm

app = typer.Typer(
    add_completion=True,
    no_args_is_help=True,
    help="RepGen — exploration-based automated bug reproduction with LLMs.",
    rich_markup_mode="rich",
)
config_app = typer.Typer(no_args_is_help=True, help="Manage RepGen configuration.")
app.add_typer(config_app, name="config")


def _prompt_framework() -> str:
    console.print("\n[bold]Select a target Python framework:[/bold]")
    fws = list_frameworks()
    for i, fw in enumerate(fws, 1):
        deps = ", ".join(fw.dependencies) if fw.dependencies else "stdlib only"
        console.print(f"  {i}) {fw.display_name}  [dim]({deps})[/dim]")
    choice = IntPrompt.ask(
        "Choice",
        choices=[str(i) for i in range(1, len(fws) + 1)],
        show_choices=False,
        default=1,
    )
    return fws[choice - 1].name


def _banner() -> None:
    console.print(
        Panel(
            "[bold white]RepGen[/bold white] — automated bug reproduction\n"
            "[dim]explore · generate · verify (no code execution)[/dim]",
            border_style="bold blue",
            subtitle=f"[dim]v{__version__}[/dim]",
            expand=False,
            padding=(1, 2),
        )
    )


def _prompt_backend() -> str:
    console.print("\n[bold]Select an LLM backend:[/bold]")
    for i, name in enumerate(BACKEND_NAMES, 1):
        client = get_backend(name)
        state = (
            "[green]configured[/green]"
            if client.is_configured()
            else "[dim]needs key[/dim]"
        )
        console.print(f"  {i}) {name}  {state}")
    choice = IntPrompt.ask(
        "Choice",
        choices=[str(i) for i in range(1, len(BACKEND_NAMES) + 1)],
        show_choices=False,
    )
    return BACKEND_NAMES[choice - 1]


def _prompt_model(backend: str) -> str:
    client = get_backend(backend)
    models = client.list_models()
    if not models:
        return Prompt.ask(f"Model for {backend}", default=client.default_model)
    return Prompt.ask(
        f"Model for {backend}", choices=models, default=client.default_model
    )


def _ensure_api_key(backend: str) -> None:
    client = get_backend(backend)
    if client.is_configured() or client.env_key is None:
        return
    console.print(f"\n[yellow]{client.env_key} not set.[/yellow]")
    key = Prompt.ask(f"Enter your {backend} API key", password=True)
    if not key:
        console.print("[error]API key required. Aborting.[/error]")
        raise typer.Exit(1)
    os.environ[client.env_key] = key


@app.command()
def run(
    bug_report: Optional[str] = typer.Option(
        None, "--bug-report", "-b", help="Path or URL to the bug report / GitHub issue."
    ),
    repo: Optional[str] = typer.Option(
        None, "--repo", "-r", help="Path or URL to the repository."
    ),
    backend: Optional[str] = typer.Option(
        None, "--backend", help=f"LLM backend ({', '.join(BACKEND_NAMES)})."
    ),
    model: Optional[str] = typer.Option(None, "--model", help="Model name."),
    commit: Optional[str] = typer.Option(
        None, "--commit", help="Git commit to checkout."
    ),
    output: Optional[str] = typer.Option(
        None, "--output", "-o", help="Output directory."
    ),
    max_attempts: Optional[int] = typer.Option(
        None, "--max-attempts", help="Max generation attempts per run."
    ),
    max_explore_steps: Optional[int] = typer.Option(
        None, "--max-explore-steps", help="Max exploration steps."
    ),
    framework: Optional[str] = typer.Option(
        None, "--framework", "-f",
        help=f"Target framework ({', '.join(FRAMEWORK_NAMES)}).",
    ),
    execute: Optional[bool] = typer.Option(
        None, "--execute/--no-execute",
        help="Plan, prepare a venv, run and verify the reproduction "
        "(default from config).",
    ),
    max_exec_retries: Optional[int] = typer.Option(
        None, "--max-exec-retries", help="Max refine/retry attempts on failure."
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Show detailed progress."
    ),
    yes: bool = typer.Option(
        False, "--yes", "-y", help="Non-interactive; fail if inputs missing."
    ),
) -> None:
    """Generate a reproduction script for a bug report + repository."""
    _banner()
    if verbose:
        configure_logging("INFO")
    cfg = RepGenConfig.load()

    backend = backend or cfg.backend
    output = output or cfg.output_dir
    max_attempts = max_attempts or cfg.max_attempts
    max_explore_steps = max_explore_steps or cfg.max_explore_steps
    framework = framework or cfg.framework
    execute = cfg.execute if execute is None else execute
    max_exec_retries = (
        cfg.max_exec_retries if max_exec_retries is None else max_exec_retries
    )

    if framework not in FRAMEWORK_NAMES:
        if yes:
            console.print(f"[error]Unknown framework '{framework}'.[/error]")
            raise typer.Exit(1)
        framework = _prompt_framework()

    if not bug_report:
        if yes:
            console.print(
                "[error]--bug-report is required in non-interactive mode.[/error]"
            )
            raise typer.Exit(1)
        bug_report = Prompt.ask("[cyan]Bug report (path or URL)[/cyan]")
    if not repo:
        if yes:
            console.print("[error]--repo is required in non-interactive mode.[/error]")
            raise typer.Exit(1)
        repo = Prompt.ask("[cyan]Repository (path or URL)[/cyan]")

    if backend not in BACKEND_NAMES:
        if yes:
            console.print(f"[error]Unknown backend '{backend}'.[/error]")
            raise typer.Exit(1)
        backend = _prompt_backend()
    if not model:
        model = cfg.model or (None if yes else _prompt_model(backend))
    if not yes:
        _ensure_api_key(backend)

    client = get_backend(backend, model)
    if not client.is_configured():
        console.print(
            f"[error]Backend '{backend}' is not configured "
            f"(set {client.env_key}).[/error]"
        )
        raise typer.Exit(1)

    reporter = RunReporter(verbose=verbose)
    exec_reporter = ExecutionReporter(verbose=verbose)
    exec_settings = ExecutionSettings(
        enabled=execute,
        max_retries=max_exec_retries,
        quick_timeout_s=cfg.quick_timeout_s,
        medium_timeout_s=cfg.medium_timeout_s,
        large_timeout_s=cfg.large_timeout_s,
    )
    service = RepGenService(output_dir=output)
    result = service.run_reproduction(
        bug_report_source=bug_report,
        repo_source=repo,
        backend=backend,
        model=model,
        commit=commit,
        max_attempts=max_attempts,
        max_explore_steps=max_explore_steps,
        progress_callback=reporter,
        execute=execute,
        framework=framework,
        exec_settings=exec_settings,
        exec_progress_callback=exec_reporter,
        # In non-interactive mode there is no one to confirm Medium/Large runs,
        # so the pipeline's built-in policy (run Quick, skip heavier) applies.
        confirm_callback=None if yes else interactive_confirm,
    )
    reporter.summary(result)
    if result.get("execution") is not None:
        exec_reporter.summary(result["execution"])
    raise typer.Exit(0 if result["success"] else 2)


@app.command()
def backends() -> None:
    """List supported LLM backends and whether they are configured."""
    table = Table(title="LLM Backends", header_style="bold magenta")
    table.add_column("Backend", style="cyan")
    table.add_column("Default model")
    table.add_column("Env var")
    table.add_column("Configured", justify="center")
    for client in list_backends():
        mark = "[green]yes[/green]" if client.is_configured() else "[red]no[/red]"
        table.add_row(
            client.name, client.default_model, client.env_key or "(keyless)", mark
        )
    console.print(table)


@app.command()
def frameworks() -> None:
    """List supported target Python frameworks."""
    table = Table(title="Frameworks", header_style="bold magenta")
    table.add_column("Name", style="cyan")
    table.add_column("Display")
    table.add_column("Base dependencies")
    table.add_column("Entrypoint")
    for fw in list_frameworks():
        table.add_row(
            fw.name,
            fw.display_name,
            ", ".join(fw.dependencies) or "(stdlib only)",
            fw.entrypoint,
        )
    console.print(table)


@app.command()
def models(
    backend: Optional[str] = typer.Option(
        None, "--backend", help=f"Backend to list models for ({', '.join(BACKEND_NAMES)})."
    ),
) -> None:
    """List suggested state-of-the-art models per backend."""
    names = [backend] if backend else BACKEND_NAMES
    for name in names:
        specs = model_specs(name)
        if not specs:
            continue
        table = Table(title=f"{name} models", header_style="bold magenta")
        table.add_column("Model ID", style="cyan")
        table.add_column("Label")
        table.add_column("Tags")
        table.add_column("Default", justify="center")
        for spec in specs:
            mark = "[green]★[/green]" if spec.default else ""
            table.add_row(spec.id, spec.label, ", ".join(spec.tags), mark)
        console.print(table)


@app.command("new")
def new_project(
    path: str = typer.Argument(..., help="Directory for the new local project."),
    framework: Optional[str] = typer.Option(
        None, "--framework", "-f",
        help=f"Framework scaffold ({', '.join(FRAMEWORK_NAMES)}).",
    ),
    force: bool = typer.Option(
        False, "--force", help="Scaffold into a non-empty directory."
    ),
) -> None:
    """Create and scaffold a new local Python project for a chosen framework."""
    from .projects import create_project

    if not framework:
        framework = _prompt_framework()
    try:
        project = create_project(path, framework=framework, exist_ok=force)
    except (FileExistsError, ValueError) as e:
        console.print(f"[error]{e}[/error]")
        raise typer.Exit(1)
    fw = get_framework(project.framework)
    console.print(
        f"[success]Created {fw.display_name} project at {project.path}[/success]"
    )
    console.print(
        f"[dim]Run: repgen run --repo {project.path} "
        f"--framework {project.framework} -b <backend>[/dim]"
    )


@app.command("open")
def open_project_cmd(
    path: str = typer.Argument(..., help="Path to an existing local project."),
) -> None:
    """Open an existing local Python project and show what RepGen detected."""
    from .projects import open_project

    try:
        project = open_project(path)
    except (FileNotFoundError, NotADirectoryError) as e:
        console.print(f"[error]{e}[/error]")
        raise typer.Exit(1)
    fw = get_framework(project.framework)
    table = Table(title=f"Project: {project.path}", header_style="bold magenta")
    table.add_column("Field", style="cyan")
    table.add_column("Value")
    table.add_row("Framework (detected)", fw.display_name)
    table.add_row("Local modules", ", ".join(project.local_modules) or "(none)")
    table.add_row("requirements.txt", "yes" if project.requirements_path.exists() else "no")
    console.print(table)
    console.print(
        f"[dim]Run: repgen run --repo {project.path} "
        f"--framework {project.framework} -b <backend>[/dim]"
    )


@app.command()
def version() -> None:
    """Print the RepGen version."""
    console.print(f"RepGen v{__version__}")


@config_app.command("show")
def config_show() -> None:
    """Show the effective configuration."""
    cfg = RepGenConfig.load()
    table = Table(title=f"Config ({config_path()})", header_style="bold magenta")
    table.add_column("Key", style="cyan")
    table.add_column("Value")
    for key, value in cfg.to_dict().items():
        table.add_row(key, str(value))
    console.print(table)


@config_app.command("path")
def config_show_path() -> None:
    """Print the configuration file path."""
    console.print(str(config_path()))


@config_app.command("init")
def config_init() -> None:
    """Create a config file with defaults."""
    cfg = RepGenConfig.load()
    path = cfg.save()
    console.print(f"[success]Wrote config to {path}[/success]")


@config_app.command("set")
def config_set(
    key: str = typer.Argument(..., help="Config key."),
    value: str = typer.Argument(..., help="New value."),
) -> None:
    """Set a configuration value (e.g. `repgen config set backend claude`)."""
    cfg = RepGenConfig.load()
    try:
        cfg.set(key, value)
    except (KeyError, ValueError) as e:
        console.print(f"[error]{e}[/error]")
        raise typer.Exit(1)
    path = cfg.save()
    console.print(f"[success]Set {key} = {value}[/success] [dim]({path})[/dim]")


def main() -> None:  # pragma: no cover - console-script compatibility shim
    app()


if __name__ == "__main__":  # pragma: no cover
    sys.exit(app())
