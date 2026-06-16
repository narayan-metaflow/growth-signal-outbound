# AGENTS.md

## Cursor Cloud specific instructions

CLI lead-gen / cold-outreach pipeline (`run.py`). No server, DB, or ports. Steps pass state via JSON files in `output/`; each step reads the prior step's output.

- Use the venv: `.venv/bin/python run.py <step>` (deps are installed there). Steps/commands are documented in `run.py` (`--help`).
- Pipeline: `discover → scrape → filter → enrich → outreach → schedule`, then a Gmail backend (`composio-*` or `gmail-*`). Run `outreach`/`schedule` after providing an `output/enriched_leads.json`.
- `discover`/`scrape`/`filter`/`enrich` require `FIRECRAWL_API_KEY` (and optionally `HUNTER_API_KEY`); unset → `RuntimeError`. The downstream `outreach`/`schedule` steps and the Gmail backend run without it.
- Gmail backend: `COMPOSIO_API_KEY` + `COMPOSIO_USER_ID` are injected via env; Gmail is already connected via Composio (`composio-drafts` creates real Gmail drafts, `composio-send` sends due queued emails). Prefer `composio-*` over the Google OAuth `gmail-*` backend (the latter needs `credentials.json` + a browser).
- `composio-send`/`gmail send` only send queue items whose `scheduled_at` is past; `config/send.json` schedules into future weekday windows, so a fresh queue often shows "0 due".
- `src/outreach.py` `SENDER` is intentionally placeholder ("Your Name"/"Your Company") — edit for real outreach.
