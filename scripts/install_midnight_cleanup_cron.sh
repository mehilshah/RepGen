#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

mkdir -p "$REPO_ROOT/logs"

CLEANUP_CMD="/bin/bash $REPO_ROOT/cleanup.sh >> $REPO_ROOT/logs/cleanup-cron.log 2>&1"
CRON_LINE="0 0 * * * $CLEANUP_CMD"

EXISTING_CRONTAB="$(crontab -l 2>/dev/null || true)"

if printf "%s\n" "$EXISTING_CRONTAB" | grep -Fq "$CLEANUP_CMD"; then
  echo "Cron job already installed:"
  echo "$CRON_LINE"
  exit 0
fi

{
  printf "%s\n" "$EXISTING_CRONTAB"
  printf "%s\n" "$CRON_LINE"
} | crontab -

echo "Installed cron job:"
echo "$CRON_LINE"
