#!/bin/bash
# For Cursor Cloud cron — send due emails and persist queue to git.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
if [[ -f .env ]]; then set -a; source .env; set +a; fi

python3 -m venv .venv 2>/dev/null || true
.venv/bin/pip install -q -r requirements.txt

if [[ ! -f send_queue.json ]]; then
  echo "ERROR: send_queue.json missing at repo root ($ROOT)" >&2
  ls -la "$ROOT" >&2
  exit 1
fi

.venv/bin/python run.py composio-send
SENT=$?

if git diff --quiet send_queue.json 2>/dev/null; then
  exit "$SENT"
fi

git config user.email "outbound-bot@users.noreply.github.com"
git config user.name "Outbound Bot"
git add send_queue.json
git commit -m "chore: update send queue after composio-send"
if ! git push origin HEAD; then
  echo "ERROR: git push failed — queue updates not persisted; disable automation to avoid duplicate sends" >&2
  exit 1
fi

exit "$SENT"
