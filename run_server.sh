#!/usr/bin/env bash
# Wrapper script to run uvicorn without reloading on changes in temp_repos
# This prevents the server from restarting when temporary repositories are cloned or updated.
uvicorn repgen.server:app --reload --reload-exclude temp_repos
