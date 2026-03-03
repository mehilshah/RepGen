# RepGen - Automated Bug Reproduction

<div align="center">

<p align="center">
  <img src="https://img.shields.io/badge/Status-Active%20Research-4CAF50?style=flat-square" />
  <img src="https://img.shields.io/badge/Python-3.12-3776AB?style=flat-square&logo=python&logoColor=white" />
 <img src="https://img.shields.io/github/actions/workflow/status/mehilshah/RepGen/ci.yml?branch=main&label=Build&style=flat-square&logo=github" />
  <img src="https://img.shields.io/badge/Execution-Dockerized-2496ED?style=flat-square&logo=docker&logoColor=white" />
  <img src="https://img.shields.io/badge/License-MIT-lightgrey?style=flat-square" />
</p>

[Features](#features) • [Quick Start](#quick-start) • [Documentation](#documentation) • [Paper](https://arxiv.org/abs/2512.14990)

</div>


## Overview

**RepGen** is a production-grade tool that leverages state-of-the-art Large Language Models (LLMs) to automatically reproduce bugs in software libraries. By analyzing bug reports and repository context, RepGen plans a reproduction strategy and generates executable Python scripts to replicate the issue.

Ideally suited for Deep Learning libraries, RepGen automates the tedious first step of debugging: creating a Minimum Reproducible Example (MRE).

## Features

- **Smart Retrieval**: Uses hybrid search (BM25 + Semantic) to find relevant code snippets and training loops for context.
- **Multi-Backend Support**: Seamlessly switch between LLM providers:
  - **OpenAI**: Utilize `gpt-4o` and `gpt-3.5-turbo` for high-precision generation.
  - **Gemini** & **Claude**: leverage multimodal and reasoning capabilities.
- **Remote Input Handling**:
  - Direct support for **GitHub Issue URLs** (fetches content via API).
  - Direct support for **Git Repository URLs** (clones automatically to temp workspace).
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



### REST API
The core engine runs as a FastAPI service.
- **Start**: `uvicorn repgen.server:app --reload --reload-dir repgen`
- **Docs**: `http://localhost:8000/docs`

### Web Dashboard
A modern, React-based UI to manage reproduction tasks visually.
- **Location**: `ui/`
- **Start**: `cd ui && npm install && npm run dev`

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

## Future Plans
* **Source-Level Bug Localization via Code Comprehension**
  Extend RepGen beyond reproduction to *pinpoint the likely source of the bug* within the repository. By combining retrieval, static analysis, and LLM-driven code comprehension, RepGen will identify suspicious functions, classes, or execution paths that are semantically aligned with the failure trace and bug report. This will reduce manual triage effort and accelerate root-cause analysis.

* **Failure-Aware Context Modeling with Execution Trace Alignment**
  Incorporate execution signals (e.g., stack traces, assertion failures, tensor shape mismatches, runtime warnings) into the reasoning loop. RepGen will align runtime evidence with repository structure to rank candidate fault locations and highlight minimal code regions responsible for the observed behavior.
