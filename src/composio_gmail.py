"""Gmail via Composio — no Google Cloud OAuth setup required."""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from rich.console import Console

from src.composio_client import get_composio, get_user_id
from src.config import OUTPUT_DIR, OUTREACH_FILE, QUEUE_FILE
from src.schedule_sends import build_queue

console = Console()


def _gmail_connected() -> bool:
    composio = get_composio()
    uid = get_user_id()
    accounts = composio.connected_accounts.list(user_ids=[uid], statuses=["ACTIVE"])
    return any(
        getattr(a.toolkit, "slug", None) == "gmail"
        for a in (accounts.items or [])
    )


def connect(auth_config_id: str | None = None) -> str:
    """Print OAuth URL if Gmail isn't connected yet."""
    if _gmail_connected():
        console.print("[green]Gmail already connected via Composio.[/green]")
        return ""

    composio = get_composio()
    auth_config_id = auth_config_id or os.environ.get("COMPOSIO_GMAIL_AUTH_CONFIG")
    if not auth_config_id:
        raise RuntimeError(
            "Gmail not connected. Create a Gmail auth config at app.composio.dev "
            "→ Auth Configs → Gmail → copy ID to COMPOSIO_GMAIL_AUTH_CONFIG, then re-run."
        )

    link = composio.connected_accounts.link(
        user_id=get_user_id(),
        auth_config_id=auth_config_id,
    )
    url = getattr(link, "redirect_url", None) or getattr(link, "redirectUrl", "")
    console.print(f"Open this URL to connect Gmail:\n{url}")
    return url


def create_drafts(queue_path: Path | None = None) -> list[dict]:
    """Create Gmail drafts from send queue via Composio."""
    queue_path = queue_path or QUEUE_FILE
    if not queue_path.exists():
        build_queue()

    composio = get_composio()
    uid = get_user_id()
    queue = json.loads(queue_path.read_text())
    created = []

    for item in queue:
        if item.get("status") in ("draft_created", "sent"):
            continue
        to = item.get("to_email")
        if not to:
            continue
        result = composio.tools.execute(
            "GMAIL_CREATE_EMAIL_DRAFT",
            user_id=uid,
            arguments={
                "recipient_email": to,
                "subject": item["subject"],
                "body": item["body"],
            },
        )
        if not result.get("successful"):
            console.print(f"[red]Failed[/red] {to}: {result.get('error')}")
            continue
        draft_id = (
            result.get("data", {})
            .get("response_data", {})
            .get("id")
        )
        item["status"] = "draft_created"
        item["gmail_draft_id"] = draft_id
        item["via"] = "composio"
        created.append(item)
        console.print(f"[green]Draft[/green] → {to} ({item['company']})")

    queue_path.write_text(json.dumps(queue, indent=2))
    console.print(
        f"\n{len(created)} drafts in Gmail. "
        "Open Gmail → Drafts → Schedule send for each (or use `run.py composio-send`)."
    )
    return created


def send_due(queue_path: Path | None = None, *, dry_run: bool = False) -> int:
    """Send queued emails whose scheduled_at has passed."""
    queue_path = queue_path or QUEUE_FILE
    if not queue_path.exists():
        outreach = OUTREACH_FILE
        if not outreach.exists():
            outreach = OUTPUT_DIR / "outreach_drafts.json"
        if outreach.exists():
            console.print("[yellow]No send queue — building from outreach drafts[/yellow]")
            build_queue(input_path=outreach, save=True)
        else:
            raise FileNotFoundError(
                f"Missing {queue_path}. Run: python run.py schedule"
            )
    queue = json.loads(queue_path.read_text())
    composio = get_composio()
    uid = get_user_id()
    now = datetime.now(ZoneInfo("UTC"))
    sent = 0

    for item in queue:
        if item.get("status") == "sent":
            continue
        when = datetime.fromisoformat(item["scheduled_at"])
        if when.tzinfo is None:
            when = when.replace(tzinfo=ZoneInfo("America/New_York"))
        if when.astimezone(ZoneInfo("UTC")) > now:
            continue
        to = item.get("to_email")
        if not to:
            continue
        if dry_run:
            console.print(f"[yellow]Would send[/yellow] → {to}")
        else:
            result = composio.tools.execute(
                "GMAIL_SEND_EMAIL",
                user_id=uid,
                arguments={
                    "recipient_email": to,
                    "subject": item["subject"],
                    "body": item["body"],
                },
            )
            if not result.get("successful"):
                console.print(f"[red]Failed[/red] {to}: {result.get('error')}")
                continue
            item["status"] = "sent"
            console.print(f"[green]Sent[/green] → {to}")
        sent += 1

    if not dry_run:
        queue_path.write_text(json.dumps(queue, indent=2))
    return sent
