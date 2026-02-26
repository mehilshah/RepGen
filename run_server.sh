#!/usr/bin/env bash
# Wrapper script to run uvicorn without reloading on changes in temp_repos
uvicorn repgen.server:app \
  --host 0.0.0.0 \
  --port 8000 \
  --reload \
  --reload-dir repgen