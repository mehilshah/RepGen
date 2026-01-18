# RepGen

<div align="center">

![RepGen Banner](https://img.shields.io/badge/RepGen-AI%20Powered%20Bug%20Reproduction-0066FF?style=for-the-badge&logo=python&logoColor=white)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Code Style: Black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Docker](https://img.shields.io/badge/docker-%230db7ed.svg?style=flat&logo=docker&logoColor=white)](https://hub.docker.com/)

**Automated Deep Learning Bug Reproduction with Large Language Models**

[Features](#-features) • [Installation](#-installation) • [Ecosystem](#-ecosystem) • [Usage](#-usage) • [Paper](https://arxiv.org/abs/2512.14990)

</div>

---

## 📖 Overview

**RepGen** is a production-grade tool that leverages state-of-the-art Large Language Models (LLMs) to automatically reproduce bugs in software libraries. By analyzing bug reports and repository context, RepGen plans a reproduction strategy and generates executable Python scripts to replicate the issue.

Ideally suited for Deep Learning libraries, RepGen automates the tedious first step of debugging: creating a Minimum Reproducible Example (MRE).

## ✨ Features

- **🔍 Smart Retrieval**: Uses hybrid search (BM25 + Semantic) to find relevant code snippets and training loops for context.
- **🤖 Multi-Backend Support**: Seamlessly switch between LLM providers:
  - **Ollama**: Run locally with models like `qwen2.5-coder`, `llama3`, or `mistral`.
  - **OpenAI**: Utilize `gpt-4o` and `gpt-3.5-turbo` for high-precision generation.
  - **Gemini**: Leverage Google's multimodal capabilities.
  - **Claude**: Use Anthropic's reasoning models.
- **🌐 Remote Input Handling**:
  - Direct support for **GitHub Issue URLs** (fetches content via API).
  - Direct support for **Git Repository URLs** (clones automatically to temp workspace).
- **🖥️ Professional UI**: A polished Terminal User Interface (TUI) powered by `rich` with interactive wizards.

---

## �️ Installation

### Prerequisites
- **Python**: 3.8 or higher
- **Git**

### Option A: Virtual Environment (Recommended)

To avoid conflicts with system packages, we recommend installing in a virtual environment.

```bash
# 1. Create a virtual environment
python3 -m venv venv

# 2. Activate it
# On Mac/Linux:
source venv/bin/activate
# On Windows:
# .\venv\Scripts\activate

# 3. Install RepGen
git clone https://github.com/mehilshah/RepGen
cd RepGen
pip install -e .
```

### Option B: Docker

Run the entire stack in an isolated container.

```bash
docker build -t repgen .
docker run -p 8000:8000 repgen
```

---

## 🌍 Ecosystem

RepGen is more than just a CLI. It provides a complete suite of tools for your workflow.

### 🔌 REST API
The core engine runs as a FastAPI service, allowing integration with other tools.
- **Start**: `uvicorn repgen.server:app --reload`
- **Docs**: `http://localhost:8000/docs`

### 🖥️ Web Dashboard
A modern, React-based UI to manage reproduction tasks visually.
- **Location**: `ui/`
- **Features**: Real-time logs, file preview, status tracking.
- **Start**: `cd ui && npm install && npm run dev`

### 🧩 Browser Extension
Injects a "Reproduce" button directly into GitHub Issues.
- **Location**: `extensions/chrome/`
- **Install**: Load unpacked in Chrome Developer Mode.

### 📝 VS Code Extension
Run RepGen directly from your editor.
- **Location**: `extensions/vscode/`
- **Install**: Open folder in VS Code and press F5 to debug/run.

---

## 🎮 Usage

### 1. Interactive CLI
The easiest way to start.
```bash
repgen
```
Follow the wizard to select your LLM backend, model, and input URLs.

### 2. Command Line Automation
For power users and scripts.
```bash
repgen \
  --bug-report https://github.com/owner/repo/issues/123 \
  --repo-path https://github.com/owner/repo.git \
  --backend openai \
  --model gpt-4o
```

### 3. Web UI
1. Start the API: `uvicorn repgen.server:app --reload`
2. Start the UI: `cd ui && npm run dev`
3. Open `http://localhost:5173`

---

## 🔑 Configuration

You can provide API keys via environment variables or the interactive CLI/UI.

```bash
export OPENAI_API_KEY="sk-..."
export GEMINI_API_KEY="AIza..."
export ANTHROPIC_API_KEY="sk-ant..."
```

## 📂 Output Structure

Results are saved to `repgen_results/` by default.

```plaintext
repgen_results/
└── <project_id>/
    ├── reproduction_script.py  # ✅ The generated script
    ├── plan.json               # 📋 Step-by-step plan
    ├── refined_bug_report.txt  # 📝 Analysis
    └── context/                # 🧩 Code snippets used
```

## 🤝 Contributing

Contributions are welcome! Please examine the `extensions/` and `ui/` directories for specific component contributions.

## 📄 License

MIT © [Mehil Shah](https://github.com/mehilshah)