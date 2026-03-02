import argparse
import os
import sys
import time

# Rich Imports
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.prompt import IntPrompt, Prompt
from rich.table import Table
from rich_argparse import RichHelpFormatter

from .core import RepGenService
from .utils import console

# Import from utils


def get_interactive_config():
    """Interactive prompt to gather missing configurations via Rich."""
    console.print(
        Panel.fit(
            "[bold cyan]RepGen Interactive Setup[/bold cyan]", border_style="cyan"
        )
    )

    # 1. Backend Selection
    backends = ["openai", "gemini", "claude"]
    console.print("\n[bold]Select LLM Backend:[/bold]")
    for i, b in enumerate(backends, 1):
        console.print(f" {i}) [green]{b.capitalize()}[/green]")

    choice = IntPrompt.ask(
        "Choice",
        choices=[str(i) for i in range(1, len(backends) + 1)],
        show_choices=False,
    )
    backend = backends[choice - 1]

    env_keys = {
        "openai": "OPENAI_API_KEY",
        "gemini": "GEMINI_API_KEY",
        "claude": "ANTHROPIC_API_KEY",
    }
    env_var = env_keys[backend]

    if not os.getenv(env_var):
        console.print(f"\n[yellow]{env_var} not found.[/yellow]")
        key = Prompt.ask(f"Enter your {backend.capitalize()} API Key", password=True)
        if key:
            os.environ[env_var] = key
        else:
            console.print("[red]API Key required. Terminating.[/red]")
            sys.exit(1)

    # Model Selection Suggestions
    suggestions = {
        "openai": ["gpt-4o", "gpt-4-turbo", "gpt-3.5-turbo"],
        "gemini": ["gemini-1.5-pro", "gemini-1.5-flash"],
        "claude": ["claude-3-5-sonnet-20240620", "claude-3-opus-20240229"],
    }

    model = Prompt.ask(
        f"Select {backend.capitalize()} Model",
        choices=suggestions[backend],
        default=suggestions[backend][0],
    )

    return backend, model


# ==========================================
# MAIN EXECUTION
# ==========================================


def main():
    # Silence internal loggers to keep the UI clean (Agent-style)
    import logging

    logging.getLogger("repgen").setLevel(logging.ERROR)

    # Styled Banner
    console.print(
        Panel(
            "[bold white]RepGen CLI: Automated Deep Learning Bug Reproduction[/bold white]\n"
            "[italic grey70]Generate reproduction scripts from bug reports automatically.[/italic grey70]",
            border_style="bold blue",
            title="[bold cyan]RepGen[/bold cyan]",
            subtitle="[dim]v1.0.0[/dim]",
            expand=False,
            padding=(1, 2),
        )
    )

    parser = argparse.ArgumentParser(
        description="RepGen CLI: Automated Bug Reproduction",
        formatter_class=RichHelpFormatter,
    )
    parser.add_argument("--bug-report", help="Path or URL to the bug report")
    parser.add_argument("--repo-path", help="Path or URL to the repository")
    parser.add_argument("--commit", help="Specific git commit ID to checkout")
    parser.add_argument(
        "--output-dir", default="./repgen_results", help="Directory for results"
    )
    parser.add_argument(
        "--backend",
        choices=["openai", "gemini", "claude"],
        help="LLM backend",
    )
    parser.add_argument("--model", help="Model name")
    parser.add_argument(
        "--max-attempts", type=int, default=3, help="Max attempts per context"
    )

    args = parser.parse_args()

    try:
        # Interactive setup if arguments are missing
        if not args.bug_report:
            args.bug_report = Prompt.ask(
                "[bold cyan]Enter URI to Bug Report file[/bold cyan] (Path or URL)"
            )
        if not args.repo_path:
            args.repo_path = Prompt.ask(
                "[bold cyan]Enter URI to Repository[/bold cyan] (Path or URL)"
            )

        if not args.backend or not args.model:
            args.backend, args.model = get_interactive_config()

        service = RepGenService(output_dir=args.output_dir)

        console.print("\n[bold]Starting Reproduction Pipeline...[/bold]")
        start_time = time.time()

        # Define UI Helper for Agent Panels
        def print_agent_panel(
            content: str, agent_name: str, color: str, title_desc: str = ""
        ):
            from rich.markdown import Markdown
            from rich.panel import Panel

            width = min(120, console.size.width - 4)

            md = Markdown(content)
            title = f"{agent_name} ({title_desc})" if title_desc else agent_name

            panel = Panel(
                md,
                title=f"[bold {color}]{title}[/bold {color}]",
                title_align="left",
                border_style=color,
                width=width,
                padding=(0, 1),
            )
            console.print(panel)

        with Progress(
            SpinnerColumn("dots", style="cyan"),
            TextColumn("[bold blue]{task.description}"),
            TimeElapsedColumn(),
            console=console,
            transient=False,
        ) as progress:
            task = progress.add_task("Initializing...", total=None)

            def progress_cb(stage, msg, data=None):
                # Update description based on stage
                stage_colors = {
                    "setup": "cyan",
                    "retrieval": "magenta",
                    "refinement": "yellow",
                    "generation": "green",
                }
                color = stage_colors.get(stage, "white")
                progress.update(
                    task, description=f"[{color}][{stage.upper()}][/] {msg}"
                )

                # Display intermediate artifacts
                if data:
                    if data.get("type") == "refined_report":
                        print_agent_panel(
                            data["content"],
                            "Refinement Agent",
                            "yellow",
                            "Bug Report processed",
                        )
                    elif data.get("type") == "plan":
                        import json

                        try:
                            plan_obj = json.loads(data["content"])
                            # Format list as a bulleted list for better readability
                            plan_text = ""
                            for step in plan_obj:
                                plan_text += f"- {step}\n"
                            print_agent_panel(
                                plan_text,
                                "Code Generation Agent",
                                "green",
                                f"Plan for Context {data.get('index')}",
                            )
                        except Exception:
                            print_agent_panel(
                                data["content"],
                                "Code Generation Agent",
                                "green",
                                f"Plan for Context {data.get('index')}",
                            )
                    elif data.get("type") == "context":
                        # Summarize context
                        summary = f"**Loaded Context {data.get('index')}**\n\n"
                        summary += f"Contains {len(data['content'].splitlines())} lines of code context."
                        print_agent_panel(
                            summary,
                            "Context Retrieval Agent",
                            "blue",
                            f"Context {data.get('index')}",
                        )
                    elif data.get("type") == "feedback":
                        print_agent_panel(
                            f"**Feedback received:** {data['content']}",
                            "Self-Correction",
                            "red",
                            "Error detected",
                        )

            result = service.run_reproduction(
                bug_report_source=args.bug_report,
                repo_source=args.repo_path,
                backend=args.backend,
                model=args.model,
                commit=args.commit,
                max_attempts=args.max_attempts,
                progress_callback=progress_cb,
            )

        end_time = time.time()
        duration = end_time - start_time

        console.print(f"\n[bold]Total Duration:[/bold] {duration:.2f} seconds\n")

        if result["success"]:
            console.print(
                Panel(
                    "[bold green]Reproduction Success![/bold green]",
                    title="System",
                    title_align="left",
                    border_style="green",
                    width=min(120, console.size.width - 4),
                )
            )

            # Display Results Table
            table = Table(
                title="Generated Files",
                show_header=True,
                header_style="bold magenta",
                width=min(120, console.size.width - 4),
            )
            table.add_column("File Name", style="cyan")
            table.add_column("Path", style="dim")
            table.add_column("Size", justify="right")

            for file_info in result["files"]:
                path = file_info["path"]
                content = file_info["content"]
                name = os.path.basename(path)
                size = f"{len(content.encode('utf-8'))} bytes"
                table.add_row(name, path, size)

            console.print(table)

            # Display File Contents
            from rich.syntax import Syntax

            for file_info in result["files"]:
                syntax = Syntax(
                    file_info["content"], "python", theme="monokai", line_numbers=True
                )

                panel = Panel(
                    syntax,
                    title=f"[bold cyan]Reproducer Code ({os.path.basename(file_info['path'])})[/bold cyan]",
                    title_align="left",
                    border_style="cyan",
                    width=min(120, console.size.width - 4),
                )
                console.print(panel)

            console.print("\n[bold green]Next Steps:[/bold green]")
            for file_info in result["files"]:
                console.print(f"  Run: [code]python {file_info['path']}[/code]")

        else:
            console.print(
                Panel(
                    f"Error: {result['error']}",
                    title="[bold red]Reproduction Failed[/bold red]",
                    title_align="left",
                    border_style="red",
                    width=min(120, console.size.width - 4),
                )
            )

    except KeyboardInterrupt:
        console.print("\n[bold red]⚠ Operation cancelled by user.[/bold red]")
        sys.exit(130)
    except Exception as e:
        console.print(f"\n[bold red]Unexpected Error:[/bold red] {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
