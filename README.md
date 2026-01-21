# RepGen - Automated Bug Reproduction

<div align="center">

<p align="center">
  <img src="https://img.shields.io/badge/Status-Active%20Research-4CAF50?style=flat-square" />
  <img src="https://img.shields.io/badge/Python-3.12-3776AB?style=flat-square&logo=python&logoColor=white" />
 <img src="https://img.shields.io/github/actions/workflow/status/mehilshah/RepGen/ci.yml?branch=main&label=Build&style=flat-square&logo=github" />
  <img src="https://img.shields.io/badge/Execution-Dockerized-2496ED?style=flat-square&logo=docker&logoColor=white" />
  <img src="https://img.shields.io/badge/License-MIT-lightgrey?style=flat-square" />
</p>

[Features](#features) • [Quick Start](#quick-start) • [VS Code](#vs-code-extension) • [Documentation](#documentation) • [Paper](https://arxiv.org/abs/2512.14990)

</div>


## Overview

**RepGen** is a production-grade tool that leverages state-of-the-art Large Language Models (LLMs) to automatically reproduce bugs in software libraries. By analyzing bug reports and repository context, RepGen plans a reproduction strategy and generates executable Python scripts to replicate the issue.

Ideally suited for Deep Learning libraries, RepGen automates the tedious first step of debugging: creating a Minimum Reproducible Example (MRE).

## Features

- **Smart Retrieval**: Uses hybrid search (BM25 + Semantic) to find relevant code snippets and training loops for context.
- **Multi-Backend Support**: Seamlessly switch between LLM providers:
  - **Ollama**: Run locally with models like `qwen2.5-coder`, `llama3`, or `mistral`.
  - **OpenAI**: Utilize `gpt-4o` and `gpt-3.5-turbo` for high-precision generation.
  - **Gemini** & **Claude**: leverage multimodal and reasoning capabilities.
- **Remote Input Handling**:
  - Direct support for **GitHub Issue URLs** (fetches content via API).
  - Direct support for **Git Repository URLs** (clones automatically to temp workspace).
- **Professional VS Code Extension**: A fully integrated sidebar to run reproductions directly in your editor.
- **Docker Ready**: Full containerization for easy deployment.

---

## Quick Start

The easiest way to run RepGen is using **Docker**. This ensures a consistent environment with all dependencies pre-installed.

```bash
# 1. Build the image
cd RepGen
docker build -t repgen .

# 2. Run the server (mounting the volume for development if needed)
docker run -p 8000:8000 repgen
```

The API will be available at `http://localhost:8000`.

---

## Developer Setup

If you prefer to run locally or contribute to the core logic:

```bash
# 1. Create a virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: .\venv\Scripts\activate

# 2. Install RepGen in editable mode
pip install -e .

# 3. Run the CLI
repgen
```

---

## VS Code Extension

RepGen includes a premium VS Code extension for a seamless workflow.

### Features
- **Persistent Sidebar**: Stays active while you work.
- **Direct Code Display**: Generated reproduction scripts appear directly in the sidebar.
- **"Open in Editor"**: One-click to open generated code in a new editor tab for review.
- **Status Tracking**:  Real-time progress indicators.

### Installation
1. Navigate to `extensions/vscode`.
2. Run `npm install` && `npm run compile`.
3. Open the folder in VS Code and press `F5` to launch the Extension Development Host.

---

## Ecosystem

### REST API
The core engine runs as a FastAPI service.
- **Start**: `uvicorn repgen.server:app --reload --reload-dir repgen`
- **Docs**: `http://localhost:8000/docs`

### Web Dashboard
A modern, React-based UI to manage reproduction tasks visually.
- **Location**: `ui/`
- **Start**: `cd ui && npm install && npm run dev`

### Browser Extension
Injects a "Reproduce" button directly into GitHub Issues.
- **Location**: `extensions/chrome/`

---

## Usage Examples

### CLI Automation
```bash
repgen \
  --bug-report https://github.com/owner/repo/issues/123 \
  --repo-path https://github.com/owner/repo.git \
  --backend openai \
  --model gpt-4o
```

### Configuration
Set API keys via environment variables:
```bash
export OPENAI_API_KEY="sk-..."
export GEMINI_API_KEY="AIza..."
```

---

## Contributing

Contributions are welcome! Please check out the issues tab or submit a PR.

## Issues

If you encounter any issues, please open a GitHub issue or contact Mehil Shah at [shahmehil@dal.ca](mailto:shahmehil@dal.ca).

## License

MIT © [Mehil Shah](https://github.com/mehilshah)
