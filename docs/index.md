# RepGen

![RepGen Banner](https://img.shields.io/badge/RepGen-AI%20Powered%20Bug%20Reproduction-0066FF?style=for-the-badge&logo=python&logoColor=white)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Code Style: Black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Docker](https://img.shields.io/badge/docker-%230db7ed.svg?style=flat&logo=docker&logoColor=white)](https://hub.docker.com/)

**Automated Deep Learning Bug Reproduction with Large Language Models**

[Paper](https://arxiv.org/abs/2512.14990)

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

## 🌍 Ecosystem

RepGen is more than just a CLI. It provides a complete suite of tools for your workflow.

### 🔌 REST API
The core engine runs as a FastAPI service, allowing integration with other tools.

### 🖥️ Web Dashboard
A modern, React-based UI to manage reproduction tasks visually.

### 🧩 Browser Extension
Injects a "Reproduce" button directly into GitHub Issues.

### 📝 VS Code Extension
Run RepGen directly from your editor.

## 🤝 Contributing

Contributions are welcome! Please examine the `extensions/` and `ui/` directories for specific component contributions.

## 📄 License

MIT © [Mehil Shah](https://github.com/mehilshah)
