import sys
from pathlib import Path
import os
import subprocess
import json
import logging
import ast
import time
import re
import requests
from typing import Tuple, Dict, Any, Optional

# Rich Imports (needed for logging in utils)
from rich.console import Console
from rich.logging import RichHandler
from rich.theme import Theme

# ==========================================
# RICH CONFIGURATION (Shared)
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
# Note: We want this configuration to be consistent
logging.basicConfig(
    level="INFO",
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(console=console, rich_tracebacks=True, markup=True)]
)
logger = logging.getLogger("repgen.utils")

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

def prepare_repository(source: str, temp_dir: Optional[str] = None) -> str: # Use a temporary directory outside the project if not provided
    if temp_dir is None:
        import tempfile
        temp_dir = tempfile.mkdtemp(prefix="repgen_")
    """
    Prepare the repository. If remote URL, clones it. If local, validates it.
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

def query_openai(prompt: str, model: str = "gpt-4o", temperature: float = 0.0, max_retries: int = 3, api_key: Optional[str] = None) -> str:
    try:
        from openai import OpenAI
    except ImportError:
        logger.error("OpenAI library not installed. Please run 'pip install openai'")
        return ""
    
    # Use provided key or env var
    api_key = api_key or os.getenv("OPENAI_API_KEY")
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

def query_gemini(prompt: str, model: str = "gemini-1.5-pro", temperature: float = 0.0, api_key: Optional[str] = None) -> str:
    api_key = api_key or os.getenv("GEMINI_API_KEY")
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
        # Note: server.py and cli.py import requests.
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        result = response.json()
        return result['candidates'][0]['content']['parts'][0]['text'].strip()
    except Exception as e:
        logger.error(f"Gemini API error: {e}")
        return ""

def query_claude(prompt: str, model: str = "claude-3-5-sonnet-20240620", temperature: float = 0.0, api_key: Optional[str] = None) -> str:
    api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
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

def query_llm(prompt: str, backend: str, model: str, api_key: Optional[str] = None) -> str:
    if backend == 'ollama':
        return query_ollama(prompt, model)
    elif backend == 'openai':
        return query_openai(prompt, model, api_key=api_key)
    elif backend == 'gemini':
        return query_gemini(prompt, model, api_key=api_key)
    elif backend == 'claude':
        return query_claude(prompt, model, api_key=api_key)
    else:
        logger.error(f"Unknown backend: {backend}")
        return ""

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

def check_relevance(bug_report: str, code: str, backend: str, model: str, api_key: Optional[str] = None) -> bool:
    prompt = f"""Analyze the provided bug report and the code segment to determine if the code segment is relevant to the bug.
            Output only JSON: {{"relevance": "yes"}} or {{"relevance": "no"}}.
            
            Bug Report: {bug_report}
            Code Segment: {code}"""
    stdout = query_llm(prompt, backend, model, api_key=api_key)
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

# Export check_ollama_status and ensure_ollama_model if needed by others
# But for now they seem local to CLI or used by query_llm (indirectly? No, interactive config uses them)
# Actually interactive config uses them. Let's move them too so interactive config in CLI can use them?
# Or keep them in CLI. query_llm calls `query_ollama` which just runs `ollama run`.
# `check_ollama_status` and `ensure_ollama_model` are helper checking functions.
# They are only used in `get_interactive_config` which is in CLI.
# So I will keep them (or move them if I move `get_interactive_config` later, but for now `get_interactive_config` is in CLI).
# Wait, `get_interactive_config` IS in CLI in my plan. So `check_ollama_status` and `ensure_ollama_model` should stay in CLI or be imported.
# It's cleaner to have them in utility if they are general, but they are used for interactive setup.
# I'll leave `get_interactive_config` and its helpers in CLI for now.
# However, `query_ollama` (moved to utils) doesn't use them.

