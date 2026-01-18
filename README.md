# RepGen CLI: Automated Deep Learning Bug Reproduction

**RepGen** is an automated CLI tool that leverages Large Language Models (LLMs) to reproduce Deep Learning (DL) bugs. It takes a bug report (URL or file) and a repository (URL or path) as input, analyzes the codebase, plans a reproduction strategy, and generates a Python script to reproduce the issue.

## ✨ Features

*   **Remote Input Support**: Accepts GitHub Issue URLs and Git Repository URLs directly.
*   **Multi-Backend Support**: Choose between:
    *   **Ollama** (Local, Private, Free)
    *   **OpenAI** (GPT-4o, GPT-3.5)
    *   **Gemini** (Google's LLM)
    *   **Claude** (Anthropic's State-of-the-Art Models)

*   **Automated Environment Management**:
    *   Checks for Ollama installation and running status.
    *   Automatically pulls missing Ollama models.
*   **Interactive UI**: A polished Terminal User Interface (TUI) powered by `rich`, featuring guided setup, progress spinners, and clean logging.
*   **Git Commit Support**: Reproduce bugs at a specific commit hash for historical accuracy.

## 🚀 Installation

### Prerequisites
*   Python 3.8+
*   Git
*   (Optional) [Ollama](https://ollama.ai) for local inference.
    
2.  **Install Dependencies:**
    It is recommended to use a virtual environment.
    
    python -m venv venv
    source venv/bin/activate  # On Windows: venv\Scripts\activate
    pip install -r requirements.txt
    

## 🎮 Usage

python repgen.py
*   **Backend**: Select your LLM provider on the fly.

### 2. Command-Line Arguments
For automation or power users, provide arguments directly:

```bash
python repgen.py \
    --bug-report https://github.com/owner/repo/issues/123 \
    --repo-path https://github.com/owner/repo.git \
    --backend ollama \
    --model qwen2.5-coder:7b \
    --commit <optional_commit_hash>
```

### Arguments Table
| Argument | Description | Required |
| :--- | :--- | :--- |
| `--bug-report` | Path to file or URL of the bug report. | Yes |
| `--repo-path` | Path to local dir or URL of the git repo. | Yes |
| `--backend` | LLM Backend: `ollama`, `openai`, `gemini`, `claude`. | No (Interactive) |
| `--model` | Specific model name (e.g., `gpt-4o`, `llama3`). | No (Interactive) |
| `--commit` | Git commit ID to checkout before analysis. | No |
| `--output-dir` | Directory to save results (default: `./repgen_results`). | No |
| `--max-attempts` | Max code generation attempts per context (default: 3). | No |

## 🔑 API Keys
For cloud backends, you can interactively enter your keys or set them as environment variables:
*   `OPENAI_API_KEY`
*   `GEMINI_API_KEY`
*   `ANTHROPIC_API_KEY`

## 📂 Output Structure
Results are saved in `./repgen_results/<project_id>/`:
*   `reproduce_<id>.py`: The final generated reproduction script.
*   `plan.json`: The step-by-step reproduction plan.
*   `refined_report.txt`: The LLM-refined bug description.
*   `context/`: Intermediate code context files retrieved from the repo.