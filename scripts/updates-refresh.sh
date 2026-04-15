#!/usr/bin/env bash
# Regenerate updates.html from the knowledge base and push if changed.
# Invoked by cron — output is appended to logs/updates-refresh.log
set -euo pipefail

REPO_DIR="/home/athena/ti-milha-marketing"
LOG_DIR="$REPO_DIR/logs"
LOG_FILE="$LOG_DIR/updates-refresh.log"

mkdir -p "$LOG_DIR"
exec >> "$LOG_FILE" 2>&1

echo "=== $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
cd "$REPO_DIR"

# Pull latest to minimise rebase conflicts with other automations.
git pull --rebase --autostash origin main || {
    echo "git pull failed, aborting"
    exit 1
}

python3 scripts/generate_updates.py

if git diff --quiet updates.html; then
    echo "No change to updates.html"
    exit 0
fi

git add updates.html
git commit -m "Auto-update updates.html from KB $(date -u +%Y-%m-%d)"
git push origin main
echo "Pushed updated updates.html"
