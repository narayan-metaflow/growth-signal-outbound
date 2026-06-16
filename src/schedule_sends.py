"""Build a timed send queue from outreach drafts."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from rich.console import Console

from src.config import OUTPUT_DIR

console = Console()

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "send.json"
DAY_MAP = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}


def load_send_config() -> dict:
    with open(CONFIG_PATH) as f:
        return json.load(f)


def _parse_hm(s: str) -> tuple[int, int]:
    h, m = s.split(":")
    return int(h), int(m)


def _next_send_days(cfg: dict, count: int, start: datetime) -> list[datetime]:
    tz = ZoneInfo(cfg["timezone"])
    now = start.astimezone(tz)
    allowed = {DAY_MAP[d.lower()] for d in cfg["send_days"]}
    h_start, m_start = _parse_hm(cfg["window_start"])
    h_end, m_end = _parse_hm(cfg["window_end"])
    gap = timedelta(minutes=cfg["minutes_between"])

    slots: list[datetime] = []
    day = now.replace(hour=h_start, minute=m_start, second=0, microsecond=0)
    if now.weekday() in allowed and now.time() > day.time().replace(hour=h_end, minute=m_end):
        day += timedelta(days=1)

    while len(slots) < count:
        if day.weekday() in allowed:
            slot = day.replace(hour=h_start, minute=m_start, second=0, microsecond=0)
            end = day.replace(hour=h_end, minute=m_end, second=0, microsecond=0)
            while slot <= end and len(slots) < count:
                if slot > now:
                    slots.append(slot)
                slot += gap
        day += timedelta(days=1)
        if day - now > timedelta(days=21):
            break
    return slots


def _dedupe_drafts(drafts: list[dict]) -> list[dict]:
    seen: set[str] = set()
    out = []
    for d in drafts:
        key = (d.get("to_email") or "").lower() or d.get("source_url") or d.get("company", "")
        if key in seen:
            continue
        seen.add(key)
        out.append(d)
    return out


def build_queue(input_path: Path | None = None, save: bool = True) -> list[dict]:
    cfg = load_send_config()
    input_path = input_path or OUTPUT_DIR / "outreach_drafts.json"
    drafts = _dedupe_drafts(json.loads(input_path.read_text()))

    if cfg.get("skip_without_email"):
        drafts = [d for d in drafts if d.get("to_email")]

    slots = _next_send_days(cfg, len(drafts), datetime.now(ZoneInfo(cfg["timezone"])))
    queue = []
    for draft, when in zip(drafts, slots):
        queue.append({
            **draft,
            "scheduled_at": when.isoformat(),
            "scheduled_display": when.strftime("%a %b %d, %Y %I:%M %p %Z"),
            "status": "pending",
        })

    console.print(f"[green]{len(queue)} emails queued[/green] ({cfg['window_start']}–{cfg['window_end']} {cfg['timezone']})")
    if queue:
        console.print(f"First: {queue[0]['scheduled_display']}")
        console.print(f"Last:  {queue[-1]['scheduled_display']}")

    if save:
        OUTPUT_DIR.mkdir(exist_ok=True)
        (OUTPUT_DIR / "send_queue.json").write_text(json.dumps(queue, indent=2))
        lines = ["| # | When | To | Company | Subject |", "|---|------|-----|---------|---------|"]
        for i, q in enumerate(queue, 1):
            lines.append(
                f"| {i} | {q['scheduled_display']} | {q.get('to_name') or '—'} "
                f"({q['to_email']}) | {q['company']} | {q['subject']} |"
            )
        (OUTPUT_DIR / "send_schedule.md").write_text("\n".join(lines) + "\n")
        console.print(f"Saved → {OUTPUT_DIR / 'send_queue.json'}")

    return queue


if __name__ == "__main__":
    build_queue()
