#!/bin/bash
# DEPRECATED — caused duplicate sends via cloud cron. Use scripts/publish-to-gmail.sh
echo "DEPRECATED. Use: bash scripts/publish-to-gmail.sh" >&2
echo "Then schedule each draft in Gmail UI. See docs/SEND.md" >&2
exit 1
