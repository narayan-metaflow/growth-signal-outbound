# Send workflow (Gmail schedule — no Cursor automation)

## Pipeline

```
discover → scrape → filter → enrich → outreach → schedule → publish
```

Or one command after outreach:

```bash
bash scripts/publish-to-gmail.sh
```

## What `publish` does

1. Builds `send_queue.json` with send times (Tue–Thu 9–11:30 AM ET, 4 min apart)
2. Creates **Gmail drafts** via Composio
3. Writes **`output/send_schedule.md`** — when to schedule each draft

## What you do in Gmail

1. Open **Gmail → Drafts**
2. Open each draft → **⋮ → Schedule send**
3. Match times in `output/send_schedule.md`

Gmail handles delivery. No cron, no cloud agent, no duplicate-send risk from ephemeral workspaces.

## Do not use

- `composio-send` / `send-daemon` / `scripts/cloud-send.sh` — immediate API send, caused duplicates
- Cursor **email send** automation — keep inactive

## Full pipeline

```bash
.venv/bin/python run.py all          # discover through schedule
.venv/bin/python run.py publish      # drafts + schedule sheet
```

## Requirements

- `COMPOSIO_API_KEY` in `.env`
- Gmail connected: `.venv/bin/python run.py composio-connect`
