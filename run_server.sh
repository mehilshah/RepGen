#!/usr/bin/env bash
# Activate virtual environment
source "$(dirname "$0")/venv/bin/activate"

# Wrapper script to run uvicorn without reloading on changes in temp_repos
exec uvicorn repgen.server:app \
  --host 0.0.0.0 \
  --port 8000 \
  --reload \
  --reload-dir repgen
