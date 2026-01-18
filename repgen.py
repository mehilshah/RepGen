import sys
from pathlib import Path
import argparse
import os
import subprocess
import json
import logging
from typing import Tuple, Dict, Any, Optional
import ast
import time
import re
import requests
import shutil

# Rich Imports
from rich.console import Console
from rich.logging import RichHandler
from rich.theme import Theme
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Prompt, Confirm, IntPrompt
from rich.table import Table
from rich import print as rprint

sys.path.insert(0, str(Path(__file__).parent))
from retrieval import RetrievalPipeline

# ==========================================
# RICH CONFIGURATION
# ==========================================

custom_theme = Theme({
    "info": "cyan",
    "warning": "yellow",
    "error": "bold red",
    "success": "bold green",
    "highlight": "magenta",
    "code": "bold white on black"
})
console = Console(theme=custom_theme)

# Configure logging to use RichHandler
logging.basicConfig(
    level="INFO",
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(console=console, rich_tracebacks=True, markup=True)]
)
logger = logging.getLogger("repgen")

# ==========================================
# INPUT HELPERS (REMOTE & LOCAL)
# ==========================================

def fetch_content(source: str) -> str:
    """
    Fetches content from a local file or a URL (e.g., GitHub Issue).
    """
    if source.startswith("http://") or source.startswith("https://"):
        # Handle GitHub Issues special case
        # GitHub URL: https://github.com/owner/repo/issues/num
        # API URL:    https://api.github.com/repos/owner/repo/issues/num
        github_issue_regex = r"github\.com/([^/]+)/([^/]+)/issues/(\d+)"
        match = re.search(github_issue_regex, source)
        
        if match:
            owner, repo, issue_num = match.groups()
            api_url = f"https://api.github.com/repos/{owner}/{repo}/issues/{issue_num}"
            console.log(f"[info]Detected GitHub Issue. Fetching from API: {api_url}[/info]")
            try:
                # Try without token first (public repos)
                response = requests.get(api_url)
                if response.status_code == 404 or response.status_code == 403:
                    # Provide token option if needed in future, for now warn
                    console.log(f"[warning]Failed to access public API ({response.status_code}).[/warning]")
                
                response.raise_for_status()
                data = response.json()
                title = data.get('title', '')
                body = data.get('body', '')
                return f"Title: {title}\n\nBody:\n{body}"
            except Exception as e:
                console.log(f"[error]Error fetching GitHub issue: {e}[/error]")
                raise
        else:
            # Generic URL
            console.log(f"[info]Fetching generic URL: {source}[/info]")
            try:
                response = requests.get(source)
                response.raise_for_status()
                return response.text
            except Exception as e:
                console.log(f"[error]Error fetching URL: {e}[/error]")
                raise
                
    else:
        # Local File
        path = Path(source)
        if not path.exists():
            raise FileNotFoundError(f"Local file not found: {path}")
        return path.read_text()

def prepare_repository(source: str, temp_dir: str = "./temp_repos") -> str:
    """
    Prepares the repository. If remote URL, clones it. If local, validates it.
    Returns the absolute path to the local repository.
    """
    if source.startswith("http://") or source.startswith("https://") or source.startswith("git@"):
        # It's a remote repo
        repo_name = source.rstrip('/').split('/')[-1].replace('.git', '')
        local_path = Path(temp_dir) / repo_name
        
        if local_path.exists():
            console.log(f"[warning]Directory {local_path} exists. Using existing content.[/warning]")
            # Optional: Pull latest? For safety, we just use it or fail if user wants fresh.
        else:
            console.log(f"[info]Cloning {source} to {local_path}...[/info]")
            try:
                subprocess.run(['git', 'clone', source, str(local_path)], check=True, capture_output=True)
                console.log(f"[success]Cloned successfully.[/success]")
            except subprocess.CalledProcessError as e:
                raise RuntimeError(f"Failed to clone repository: {e}")
        
        return str(local_path.resolve())
    else:
        # Local Path
        path = Path(source).resolve()
        if not path.exists():
            raise FileNotFoundError(f"Repository path not found: {path}")
        return str(path)

# ==========================================
# LLM BACKENDS
# ==========================================

def query_ollama(prompt: str, model: str) -> str:
    try:
        cmd = ['ollama', 'run', model]
        process = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8')
        stdout, stderr = process.communicate(input=prompt)
        if process.returncode != 0:
            logger.error(f"Ollama Error ({model}): {stderr.strip()}")
            return ""
        return stdout.strip()
    except Exception as e:
        logger.error(f"Ollama execution failed: {e}")
        return ""

def query_openai(prompt: str, model: str = "gpt-4o", temperature: float = 0.0, max_retries: int = 3) -> str:
    try:
        from openai import OpenAI
    except ImportError:
        logger.error("OpenAI library not installed. Please run 'pip install openai'")
        return ""
    
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.error("OPENAI_API_KEY environment variable not set")
        return ""
    
    for attempt in range(max_retries):
        try:
            client = OpenAI(api_key=api_key)
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                max_tokens=4096,
            )
            content = response.choices[0].message.content
            return content.strip() if content else ""
        except Exception as e:
            logger.warning(f"OpenAI API error (attempt {attempt+1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
            else:
                logger.error("Max retries reached for OpenAI API")
    return ""

def query_gemini(prompt: str, model: str = "gemini-1.5-pro", temperature: float = 0.0) -> str:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        logger.error("GEMINI_API_KEY environment variable not set")
        return ""
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    headers = {'Content-Type': 'application/json'}
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": temperature}
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        result = response.json()
        return result['candidates'][0]['content']['parts'][0]['text'].strip()
    except Exception as e:
        logger.error(f"Gemini API error: {e}")
        return ""

def query_claude(prompt: str, model: str = "claude-3-5-sonnet-20240620", temperature: float = 0.0) -> str:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        logger.error("ANTHROPIC_API_KEY environment variable not set")
        return ""
    
    url = "https://api.anthropic.com/v1/messages"
    headers = {
        'x-api-key': api_key,
        'anthropic-version': '2023-06-01',
        'content-type': 'application/json'
    }
    payload = {
        "model": model,
        "max_tokens": 4096,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        result = response.json()
        return result['content'][0]['text'].strip()
    except Exception as e:
        logger.error(f"Claude API error: {e}")
        return ""

def query_llm(prompt: str, backend: str, model: str) -> str:
    if backend == 'ollama':
        return query_ollama(prompt, model)
    elif backend == 'openai':
        return query_openai(prompt, model)
    elif backend == 'gemini':
        return query_gemini(prompt, model)
    elif backend == 'claude':
        return query_claude(prompt, model)
    else:
        logger.error(f"Unknown backend: {backend}")
        return ""

# ==========================================
# INTERACTIVE UI HELPERS
# ==========================================

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

# ==========================================
# PROMPT BUILDERS
# ==========================================

def create_prompt_refinement(bug_report_content):
    return f"""You are a software development assistant. Analyze and restructure this bug report.
 
Original bug report:
{bug_report_content}
 
Provide your analysis in exactly this format:
 
TITLE
[One-line summary of the core issue]
 
SYMPTOMS
• [List each observed problem]
• [Include error messages exactly as shown]
• [Include all reported unexpected behaviors]
 
EXPECTED BEHAVIOR
[Describe what should happen when the software works correctly]
 
REPRODUCTION STEPS
1. [First step to reproduce]
2. [Next step]
3. [Continue until complete]
 
Begin your structured analysis:"""

def create_prompt_plan(bug_report_content, context):
    if 'main_file' in context:
        file_paths = [context['main_file']['path']]
        file_contents = [context['main_file']['content']]
        dependencies = context.get('dependencies', [])
        dep_string = "\n\nImport Dependencies:\n" + json.dumps(dependencies, indent=2) if dependencies else ""
    elif 'module' in context:
        file_paths = [file['path'] for file in context['module']['files']]
        file_contents = [snippet['code'] for file in context['module']['files'] for snippet in file['snippets']]
        dep_string = ""
    else:
        file_paths = []
        file_contents = []
        dep_string = ""

    file_paths_string = "\n\n".join([f"Module Path {i+1}:\n{json.dumps(path, indent=2)}" for i, path in enumerate(file_paths)])
    file_contents_string = "\n\n".join([f"Code Context {i+1}:\n{json.dumps(content, indent=2)}" for i, content in enumerate(file_contents)])

    return f"""You are a code generation planner. Create a detailed step-by-step plan to reproduce this bug. Focus on concrete, technical steps with specific values and assertions.
 
Bug Report:
{bug_report_content}
 
{file_paths_string}
 
{file_contents_string}{dep_string}
 
Your task is to create a precise technical plan that an LLM can follow to generate code that reproduces this bug. Each step should be specific and actionable.
 
Requirements:
- Include specific technical details (e.g., dimensions, batch sizes, function parameters)
- Focus only on reproducing the bug, not fixing it
- Include setup steps (imports, data preparation)
- Include validation steps to verify the bug occurs
- Make steps granular and specific
 
Output must be a valid JSON array of strings, formatted like this example:
[
    "Import TensorFlow and the inception module from inception_test.py",
    "Define a batch size of 5 and image dimensions of 299x299",
    "Create random uniform input data with shape (batch_size, height, width, 3)",
    "Call inception_v3 function with num_classes=1000",
    "Verify output contains NaN values in loss calculation"
]
 
Generate plan steps:"""

def _build_prompt(bug_report: str, code_context: str, plan: str, feedback: str = "") -> str:
    prompt = f"""You are a senior software engineer fluent in reproducing deep learning bugs. Generate a code snippet to reproduce this bug:

            Bug Report:
            {bug_report}

            Relevant Code Context:
            {code_context}

            Reproduction Plan:
            {plan}"""

    if feedback:
        prompt += f"""

            Previous Attempt Feedback:
            {feedback}"""

    prompt += """

            Requirements:
            1. Minimal Python script
            2. Include necessary setup
            3. Do not add any explanation comments, pure code, nothing else.
            4. Use standard libraries where possible
            5. Mention dependencies in comments if needed
            6. Do not generate any code for the module, use the existing imports.
            7. Use the existing imports and their respective methods from the main file to generate the code snippet.
            8. Output ONLY the code without explanation:"""
    return prompt

# ==========================================
# VERIFICATION HELPERS
# ==========================================

def check_structural_correctness(code: str) -> tuple[bool, str]:
    try:
        ast.parse(code)
        return True, ""
    except SyntaxError as e:
        error_msg = f"Syntax Error: {e.msg}\nLine {e.lineno}: {e.text.strip() if e.text else 'N/A'}"
        return True, error_msg # RETURN TRUE anyway to allow feedback loop, but log error
    except Exception as e:
        return False, f"Structural Error: {str(e)}"

def extract_json_content(text):
    pattern = r'```(?:json)?\s*(.*?)\s*```'
    match = re.search(pattern, text, re.DOTALL)
    if match: return match.group(1)
    if text.strip().startswith("{") and text.strip().endswith("}"): return text.strip()
    if text.strip().startswith("[") and text.strip().endswith("]"): return text.strip()
    return None

def check_relevance(bug_report: str, code: str, backend: str, model: str) -> bool:
    prompt = f"""Analyze the provided bug report and the code segment to determine if the code segment is relevant to the bug.
            Output only JSON: {{"relevance": "yes"}} or {{"relevance": "no"}}.
            
            Bug Report: {bug_report}
            Code Segment: {code}"""
    stdout = query_llm(prompt, backend, model)
    try:
        json_str = extract_json_content(stdout) or stdout
        response = json.loads(json_str)
        return response.get('relevance', '').lower() == 'yes'
    except:
        return 'yes' in stdout.lower()

# ==========================================
# GIT HELPERS
# ==========================================

def checkout_commit(repo_path: str, commit: str) -> bool:
    try:
        logger.info(f"Checking out commit: {commit}")
        # Check if it's a git repo
        if not (Path(repo_path) / ".git").exists():
            logger.error(f"Not a git repository: {repo_path}")
            return False
        
        # Run git checkout
        subprocess.run(['git', 'checkout', commit], cwd=repo_path, check=True, capture_output=True, text=True)
        console.log(f"[success]Successfully checked out {commit}[/success]")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Git checkout failed: {e.stderr.strip()}")
        return False
    except Exception as e:
        logger.error(f"Error during git checkout: {e}")
        return False

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

    # --- 1. PREPARE INPUTS ---
    try:
        with console.status("[bold green]Fetching Bug Report...[/bold green]"):
            bug_report_content = fetch_content(args.bug_report)
        console.print("[info]Bug Report Fetched successfully.[/info]")
        
        with console.status("[bold green]Preparing Repository...[/bold green]"):
            local_repo_path = prepare_repository(args.repo_path)
        console.print(f"[info]Repository ready at: {local_repo_path}[/info]")
        
        # Git Checkout if needed
        if args.commit:
            with console.status(f"[bold green]Checking out commit {args.commit}...[/bold green]"):
                if not checkout_commit(local_repo_path, args.commit):
                    console.print("[red]Failed to checkout commit. Aborting.[/red]")
                    return

    except Exception as e:
        console.print(f"[bold red]Initialization Failed:[/bold red] {e}")
        return

    # --- 2. INITIALIZE PIPELINE ---
    try:
        # We must save the bug report to a temp file because Pipeline expects a path
        # But wait, Config now expects bug_report_path to identify project ID.
        # We can construct a proxy object or just write it to disk. 
        # Simpler: Write it to the output dir immediately.
        
        # Initial 'temp' ID just to get a path
        temp_project_id = f"RepGen_Run_{int(time.time())}"
        temp_out_dir = Path(args.output_dir) / temp_project_id
        temp_out_dir.mkdir(parents=True, exist_ok=True)
        
        local_bug_report_path = temp_out_dir / "input_bug_report.txt"
        local_bug_report_path.write_text(bug_report_content)
        
        pipeline = RetrievalPipeline(
            repo_path=local_repo_path,
            bug_report_path=str(local_bug_report_path),
            output_dir=args.output_dir
        )
    except Exception as e:
        console.print(f"[bold red]Pipeline Init Failed:[/bold red] {e}")
        return

    project_id = pipeline.config.PROJECT_ID
    console.print(Panel(f"Project ID: [bold magenta]{project_id}[/bold magenta]", title="Pipeline Initialized"))

    # --- 3. RETRIEVAL ---
    with console.status("[bold yellow]Running Retrieval Pipeline...[/bold yellow]"):
        ret_result = pipeline.run_pipeline()
    
    if not ret_result:
        console.print("[bold red]Retrieval failed to find relevant code.[/bold red]")
        return
    
    # --- 4. REFINEMENT ---
    with console.status("[bold yellow]Refining Bug Report with LLM...[/bold yellow]"):
        refined_report = query_llm(create_prompt_refinement(bug_report_content), args.backend, args.model)
        if not refined_report:
            console.print("[warning]Refinement failed, using original report.[/warning]")
            refined_report = bug_report_content
        
        refined_report_path = pipeline.config.REFINED_BUG_REPORT_DIR_OUT / "refined_report.txt"
        refined_report_path.write_text(refined_report)
    console.print("[success]Bug Report Refined.[/success]")

    # --- 5. GENERATION LOOP (Progress Bar) ---
    context_files = sorted(list(pipeline.config.CONTEXT_DIR_OUT.glob("*.json")))
    if not context_files:
        console.print("[bold red]No context files generated. Reproduction impossible.[/bold red]")
        return

    console.print(f"[info]Found {len(context_files)} context files. Starting generation...[/info]")
    
    successful_gen = False
    
    for idx, ctx_file in enumerate(context_files, 1):
        ctx_num = ctx_file.stem.split('_')[-1]
        console.rule(f"[bold blue]Processing Context {idx}/{len(context_files)} (ID: {ctx_num})[/bold blue]")
        
        with open(ctx_file, 'r') as f:
            ctx_content = f.read()
        
        # Plan
        with console.status("[cyan]Generating Reproduction Plan...[/cyan]"):
            plan_raw = query_llm(create_prompt_plan(refined_report, json.loads(ctx_content)), args.backend, args.model)
            plan = extract_json_content(plan_raw) or "[]"
        
        console.print(f"[bold]Plan generated.[/bold]")
        
        # Attempts
        prompt_code = _build_prompt(refined_report, ctx_content, plan)
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=True,
            console=console
        ) as progress:
            
            task = progress.add_task(f"Attempting generation (Max {args.max_attempts})...", total=args.max_attempts)
            
            for attempt in range(1, args.max_attempts + 1):
                progress.update(task, description=f"Context {ctx_num} | Attempt {attempt}/{args.max_attempts}")
                
                raw_code_output = query_llm(prompt_code, args.backend, args.model)
                code = extract_json_content(raw_code_output) or raw_code_output
                
                # Check
                is_valid, err = check_structural_correctness(code)
                if not is_valid: # Syntax error but we might be strict
                     # Actually check_structural_correctness above returns True, err for logging?
                     # Wait, I updated it to True, err. If it returns False, it's a fatal ast error?
                     # Let's verify logic:
                     # old logic: return False, err.
                     # I changed it to return True, err? No, I see it on line 538.
                     # Let's revert to standard logic: if syntax error -> retry.
                    pass 

                if err:
                     progress.console.print(f"[yellow]Attempt {attempt} Syntax warning: {err.splitlines()[0]}[/yellow]")
                     prompt_code = _build_prompt(refined_report, ctx_content, plan, feedback=f"Syntax Error: {err}")
                     progress.advance(task)
                     continue
                
                # Relevance
                if not check_relevance(refined_report, code, args.backend, args.model):
                     progress.console.print(f"[yellow]Attempt {attempt} Code deemed irrelevant.[/yellow]")
                     progress.advance(task)
                     continue
                
                # Success
                out_file = pipeline.config.REPRODUCTION_DIR_OUT / f"reproduce_{ctx_num}.py"
                out_file.write_text(code)
                
                # Main result
                final_file = Path(args.output_dir) / f"reproduce_{project_id}.py"
                final_file.write_text(code)
                
                console.print(Panel(f"[bold green]SUCCESS![/bold green]\nGenerated reproduction script for Context {ctx_num} at:\n{final_file}", border_style="green"))
                successful_gen = True
                break
        
        if successful_gen:
            break

    if not successful_gen:
        console.print("[bold red]Failed to generate a valid reproduction script after all attempts.[/bold red]")

if __name__ == "__main__":
    main()
