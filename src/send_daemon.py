"""Wait and send emails at their scheduled_at times."""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from rich.console import Console

from src.composio_client import get_composio, get_user_id
from src.config import OUTPUT_DIR

console = Console()


def _parse_when(iso: str) -> datetime:
    dt = datetime.fromisoformat(iso)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo("America/New_York"))
    return dt


def run_daemon(queue_path: Path | None = None) -> None:
    queue_path = queue_path or OUTPUT_DIR / "send_queue.json"
    composio = get_composio()
    uid = get_user_id()

    console.print("[bold]Send daemon started[/bold] — will send at scheduled times (Ctrl+C to stop)")

    while True:
        queue = json.loads(queue_path.read_text())
        pending = [q for q in queue if q.get("status") not in ("sent", "cancelled") and q.get("to_email")]
        if not pending:
            console.print("[green]All emails sent.[/green]")
            break

        now = datetime.now(ZoneInfo("UTC"))
        next_item = min(pending, key=lambda q: _parse_when(q["scheduled_at"]))
        when = _parse_when(next_item["scheduled_at"]).astimezone(ZoneInfo("UTC"))
        wait_secs = (when - now).total_seconds()

        if wait_secs > 0:
            console.print(
                f"Next: {next_item['to_email']} ({next_item['company']}) "
                f"at {next_item['scheduled_display']} — waiting {int(wait_secs // 60)}m {int(wait_secs % 60)}s"
            )
            time.sleep(min(wait_secs, 60))
            continue

        to = next_item["to_email"]
        console.print(f"[cyan]Sending[/cyan] → {to} ({next_item['company']})")
        result = composio.tools.execute(
            "GMAIL_SEND_EMAIL",
            user_id=uid,
            arguments={
                "recipient_email": to,
                "subject": next_item["subject"],
                "body": next_item["body"],
            },
        )
        if result.get("successful"):
            for item in queue:
                if item.get("to_email") == to and item.get("scheduled_at") == next_item["scheduled_at"]:
                    item["status"] = "sent"
                    item["sent_at"] = datetime.now(ZoneInfo("UTC")).isoformat()
            queue_path.write_text(json.dumps(queue, indent=2))
            console.print(f"[green]Sent[/green] → {to}")
        else:
            console.print(f"[red]Failed[/red] {to}: {result.get('error')}")
            for item in queue:
                if item.get("to_email") == to and item.get("scheduled_at") == next_item["scheduled_at"]:
                    item["status"] = "failed"
            queue_path.write_text(json.dumps(queue, indent=2))

        time.sleep(2)


if __name__ == "__main__":
    run_daemon()
