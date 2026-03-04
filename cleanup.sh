#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$SCRIPT_DIR"
LOG_DIR="$REPO_ROOT/logs"

mkdir -p "$LOG_DIR"

human_bytes() {
  local bytes="$1"
  local units=("B" "KB" "MB" "GB" "TB")
  local i=0
  local value="$bytes"
  while (( value >= 1024 && i < ${#units[@]} - 1 )); do
    value=$((value / 1024))
    i=$((i + 1))
  done
  printf "%s %s" "$value" "${units[$i]}"
}

safe_du_sum() {
  local total=0
  local path=""
  for path in "$@"; do
    if [[ -e "$path" ]]; then
      total=$((total + $(du -sb "$path" 2>/dev/null | awk '{print $1}')))
    fi
  done
  echo "$total"
}

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting cleanup..."

shopt -s nullglob
TMP_TARGETS=(/tmp/repgen_*)
shopt -u nullglob

PYCACHE_DIRS=()
while IFS= read -r d; do
  PYCACHE_DIRS+=("$d")
done < <(find "$REPO_ROOT" -type d \( -name "__pycache__" -o -name ".pytest_cache" \) 2>/dev/null || true)

RESULTS_DIR="$REPO_ROOT/repgen_results"
TEMP_REPOS_DIR="$REPO_ROOT/temp_repos"

BEFORE_TMP_BYTES="$(safe_du_sum "${TMP_TARGETS[@]}")"
BEFORE_RESULTS_BYTES="$(safe_du_sum "$RESULTS_DIR")"
BEFORE_TEMP_REPOS_BYTES="$(safe_du_sum "$TEMP_REPOS_DIR")"
BEFORE_PYCACHE_BYTES="$(safe_du_sum "${PYCACHE_DIRS[@]}")"

BEFORE_TOTAL=$((BEFORE_TMP_BYTES + BEFORE_RESULTS_BYTES + BEFORE_TEMP_REPOS_BYTES + BEFORE_PYCACHE_BYTES))

if ((${#TMP_TARGETS[@]} > 0)); then
  rm -rf "${TMP_TARGETS[@]}"
fi

if [[ -d "$RESULTS_DIR" ]]; then
  find "$RESULTS_DIR" -mindepth 1 -maxdepth 1 -exec rm -rf {} +
fi

if [[ -d "$TEMP_REPOS_DIR" ]]; then
  find "$TEMP_REPOS_DIR" -mindepth 1 -maxdepth 1 -exec rm -rf {} +
fi

if ((${#PYCACHE_DIRS[@]} > 0)); then
  rm -rf "${PYCACHE_DIRS[@]}"
fi

AFTER_TMP_BYTES="$(safe_du_sum "${TMP_TARGETS[@]}")"
AFTER_RESULTS_BYTES="$(safe_du_sum "$RESULTS_DIR")"
AFTER_TEMP_REPOS_BYTES="$(safe_du_sum "$TEMP_REPOS_DIR")"
AFTER_PYCACHE_BYTES="$(safe_du_sum "${PYCACHE_DIRS[@]}")"

AFTER_TOTAL=$((AFTER_TMP_BYTES + AFTER_RESULTS_BYTES + AFTER_TEMP_REPOS_BYTES + AFTER_PYCACHE_BYTES))
RECLAIMED_BYTES=$((BEFORE_TOTAL - AFTER_TOTAL))
if ((RECLAIMED_BYTES < 0)); then
  RECLAIMED_BYTES=0
fi

echo "Cleanup complete."
echo "Removed:"
echo "  - /tmp/repgen_*: $(human_bytes "$((BEFORE_TMP_BYTES - AFTER_TMP_BYTES))")"
echo "  - repgen_results/: $(human_bytes "$((BEFORE_RESULTS_BYTES - AFTER_RESULTS_BYTES))")"
echo "  - temp_repos/: $(human_bytes "$((BEFORE_TEMP_REPOS_BYTES - AFTER_TEMP_REPOS_BYTES))")"
echo "  - Python caches (__pycache__, .pytest_cache): $(human_bytes "$((BEFORE_PYCACHE_BYTES - AFTER_PYCACHE_BYTES))")"
echo "Total space reclaimed: $(human_bytes "$RECLAIMED_BYTES") ($RECLAIMED_BYTES bytes)"
