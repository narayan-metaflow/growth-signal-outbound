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

_configure_git_push() {
  if [[ -n "${GITHUB_TOKEN:-}" ]]; then
    git remote set-url origin "https://x-access-token:${GITHUB_TOKEN}@github.com/narayan-metaflow/growth-signal-outbound.git"
  elif [[ -n "${GIT_SSH_PRIVATE_KEY:-}" ]]; then
    local keyfile
    keyfile="$(mktemp)"
    trap 'rm -f "$keyfile"' EXIT
    printf '%s\n' "$GIT_SSH_PRIVATE_KEY" > "$keyfile"
    chmod 600 "$keyfile"
    export GIT_SSH_COMMAND="ssh -i $keyfile -o StrictHostKeyChecking=accept-new"
    git remote set-url origin "git@github.com:narayan-metaflow/growth-signal-outbound.git"
  fi
}

.venv/bin/python run.py composio-send
SENT=$?

if git diff --quiet send_queue.json 2>/dev/null; then
  exit "$SENT"
fi

git config user.email "outbound-bot@users.noreply.github.com"
git config user.name "Outbound Bot"
git add send_queue.json
git commit -m "chore: update send queue after composio-send"
_configure_git_push
if ! git push origin HEAD; then
  echo "ERROR: git push failed — add GITHUB_TOKEN or GIT_SSH_PRIVATE_KEY to Cursor Cloud secrets" >&2
  exit 1
fi

exit "$SENT"
