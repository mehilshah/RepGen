# Usage

## Interactive CLI
The easiest way to start.
```bash
repgen
```
Follow the wizard to select your LLM backend, model, and input URLs.

## Command Line Automation
For power users and scripts.
```bash
repgen \
  --bug-report https://github.com/owner/repo/issues/123 \
  --repo-path https://github.com/owner/repo.git \
  --backend openai \
  --model gpt-4o
```

## Web UI
1. Start the API: `uvicorn repgen.server:app --reload`
2. Start the UI: `cd ui && npm run dev`
3. Open `http://localhost:5173`

## Configuration

You can provide API keys via environment variables or the interactive CLI/UI.

```bash
export OPENAI_API_KEY="sk-..."
export GEMINI_API_KEY="AIza..."
export ANTHROPIC_API_KEY="sk-ant..."
```

## Output Structure

Results are saved to `repgen_results/` by default.

```plaintext
repgen_results/
└── <project_id>/
    ├── reproduction_script.py  # ✅ The generated script
    ├── plan.json               # 📋 Step-by-step plan
    ├── refined_bug_report.txt  # 📝 Analysis
    └── context/                # 🧩 Code snippets used
```
