#!/bin/bash
# For Cursor Cloud cron — send due emails and persist queue to git.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
if [[ -f .env ]]; then set -a; source .env; set +a; fi

.venv/bin/python run.py composio-send
SENT=$?

if git diff --quiet output/send_queue.json 2>/dev/null; then
  exit "$SENT"
fi

git config user.email "outbound-bot@users.noreply.github.com"
git config user.name "Outbound Bot"
git add output/send_queue.json
git commit -m "chore: update send queue after composio-send"
git push origin HEAD

exit "$SENT"
