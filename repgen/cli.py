import sys
from pathlib import Path
import argparse
import os
import subprocess
import logging
from typing import Tuple, Dict, Any, Optional

# Rich Imports
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Prompt, Confirm, IntPrompt
from rich import print as rprint

# Import from utils
from .utils import (
    console, logger, # Re-use the same console/logger
    fetch_content, prepare_repository, checkout_commit, query_llm,
    check_structural_correctness, extract_json_content, check_relevance
)
from .core import RepGenService

# ==========================================
# INTERACTIVE UI HELPERS
# ==========================================

def check_ollama_status():
    try:
        subprocess.run(['ollama', '--version'], capture_output=True, check=True)
        return True
    except:
        return False

def ensure_ollama_model(model: str):
    try:
        result = subprocess.run(['ollama', 'list'], capture_output=True, text=True)
        if model not in result.stdout:
            console.print(f"[yellow]Model {model} not found. Pulling...[/yellow]")
            subprocess.run(['ollama', 'pull', model], check=True)
            console.print(f"[green]Successfully pulled {model}[/green]")
    except Exception as e:
        console.print(f"[red]Error checking/pulling model: {e}[/red]")

def get_interactive_config():
    """Interactive prompt to gather missing configurations via Rich."""
    console.print(Panel.fit("[bold cyan]RepGen Interactive Setup[/bold cyan]", border_style="cyan"))
    
    # 1. Backend Selection
    backends = ['ollama', 'openai', 'gemini', 'claude']
    console.print("\n[bold]Select LLM Backend:[/bold]")
    for i, b in enumerate(backends, 1):
        console.print(f" {i}) [green]{b.capitalize()}[/green]")
    
    choice = IntPrompt.ask("Choice", choices=[str(i) for i in range(1, len(backends)+1)], show_choices=False)
    backend = backends[choice-1]
    
    # 2. Environment & Key Setup
    model = ""
    if backend == 'ollama':
        with console.status("[bold green]Checking Ollama status...[/bold green]"):
            is_installed = check_ollama_status()
        
        if not is_installed:
            console.print("[bold red]Error: Ollama is not installed or not running.[/bold red]")
            if Confirm.ask("Would you like me to try installing it via Homebrew?"):
                try:
                    subprocess.run(['brew', 'install', 'ollama'], check=True)
                    console.print("[green]Ollama installed. Please start it logic and try again.[/green]")
                except:
                    console.print("[red]Installation failed. Please install manually.[/red]")
                sys.exit(1)
            else:
                sys.exit(1)
        
        model = Prompt.ask("Ollama Model", default="qwen2.5-coder:7b")
        with console.status(f"[bold green]Ensuring model {model} is available...[/bold green]"):
            ensure_ollama_model(model)
        
    else:
        env_keys = {
            'openai': 'OPENAI_API_KEY',
            'gemini': 'GEMINI_API_KEY',
            'claude': 'ANTHROPIC_API_KEY'
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
            'openai': ['gpt-4o', 'gpt-4-turbo', 'gpt-3.5-turbo'],
            'gemini': ['gemini-1.5-pro', 'gemini-1.5-flash'],
            'claude': [ 'claude-3-5-sonnet-20240620', 'claude-3-opus-20240229']
        }
        
        model = Prompt.ask(f"Select {backend.capitalize()} Model", choices=suggestions[backend], default=suggestions[backend][0])
            
    return backend, model


# ==========================================
# MAIN EXECUTION
# ==========================================

def main():
    console.print(Panel.fit("[bold blue]RepGen CLI: Automated Deep Learning Bug Reproduction[/bold blue]", border_style="blue"))
    
    parser = argparse.ArgumentParser(description="RepGen CLI")
    parser.add_argument("--bug-report", help="Path or URL to the bug report")
    parser.add_argument("--repo-path", help="Path or URL to the repository")
    parser.add_argument("--commit", help="Specific git commit ID to checkout")
    parser.add_argument("--output-dir", default="./repgen_results", help="Directory for results")
    parser.add_argument("--backend", choices=['ollama', 'openai', 'gemini', 'claude'], help="LLM backend")
    parser.add_argument("--model", help="Model name")
    parser.add_argument("--max-attempts", type=int, default=3, help="Max attempts per context")
    
    args = parser.parse_args()

    # Interactive setup if arguments are missing
    if not args.bug_report:
        args.bug_report = Prompt.ask("Enter URI to Bug Report file (Path or URL)")
    if not args.repo_path:
        args.repo_path = Prompt.ask("Enter URI to Repository (Path or URL)")
        
    if not args.backend or not args.model:
        args.backend, args.model = get_interactive_config()

    service = RepGenService(output_dir=args.output_dir)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=False,
        console=console
    ) as progress:
        task = progress.add_task("Running Reproduction...", total=None)

        def progress_cb(stage, msg):
            progress.update(task, description=f"[{stage.upper()}] {msg}")
            console.log(f"[{stage}] {msg}")

        result = service.run_reproduction(
            bug_report_source=args.bug_report,
            repo_source=args.repo_path,
            backend=args.backend,
            model=args.model,
            commit=args.commit,
            max_attempts=args.max_attempts,
            progress_callback=progress_cb
        )

    if result["success"]:
        console.print(Panel(f"[bold green]SUCCESS![/bold green]\nGenerated reproduction scripts:\n" + "\n".join(result["files"]), border_style="green"))
    else:
        console.print(Panel(f"[bold red]FAILED[/bold red]\nError: {result['error']}", border_style="red"))

if __name__ == "__main__":
    main()
