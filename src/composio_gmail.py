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
from src.validators import is_fake_email, is_fake_phone

console = Console()

DONE_STATUSES = frozenset({"sent", "failed", "skipped", "cancelled", "sending"})


def _save_queue(queue_path: Path, queue: list[dict]) -> None:
    queue_path.write_text(json.dumps(queue, indent=2))


def _should_send(item: dict) -> bool:
    if item.get("status") in DONE_STATUSES:
        return False
    email = item.get("to_email")
    if not email or is_fake_email(email) or is_fake_phone(item.get("to_phone")):
        return False
    return True


def _verify_recipient(email: str) -> tuple[bool, str | None]:
    if os.environ.get("HUNTER_API_KEY"):
        try:
            from src.hunter_client import is_deliverable, verify_email

            data = verify_email(email)
            if data and not is_deliverable(email):
                result = data.get("result") or "invalid"
                return False, f"hunter:{result}"
        except Exception:
            pass
    return True, None


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
        if item.get("status") in ("draft_created", "sent", "scheduled", "cancelled", "skipped"):
            continue
        to = item.get("to_email")
        if not to or is_fake_email(to) or is_fake_phone(item.get("to_phone")):
            item["status"] = "skipped"
            item["skip_reason"] = "placeholder_contact"
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

    _save_queue(queue_path, queue)
    console.print(f"\n[bold]{len(created)} drafts in Gmail[/bold]")
    console.print(
        "Schedule in Gmail (no Cursor automation):\n"
        "  1. Open Gmail → Drafts\n"
        "  2. Open each draft → ⋮ → Schedule send\n"
        "  3. Use times in output/send_schedule.md"
    )
    return created


def print_schedule_guide(queue_path: Path | None = None) -> None:
    """Print when to schedule each draft in Gmail."""
    queue_path = queue_path or QUEUE_FILE
    schedule_md = OUTPUT_DIR / "send_schedule.md"
    if schedule_md.exists():
        console.print(f"\nSchedule times → {schedule_md}")
    queue = json.loads(queue_path.read_text())
    pending = [
        q for q in queue
        if q.get("status") in ("pending", "draft_created") and q.get("to_email")
    ]
    if not pending:
        return
    console.print("\n| When | To | Company |")
    console.print("|------|-----|---------|")
    for q in pending:
        console.print(
            f"| {q.get('scheduled_display', '—')} | {q['to_email']} | {q.get('company', '—')} |"
        )


def send_due(queue_path: Path | None = None, *, dry_run: bool = False) -> int:
    """Send queued emails whose scheduled_at has passed. Each address sends at most once."""
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
        if item.get("status") == "sending":
            console.print(f"[yellow]Skip in-flight[/yellow] {item.get('to_email')}")
            continue
        if not _should_send(item):
            if item.get("status") not in DONE_STATUSES and (
                is_fake_email(item.get("to_email")) or is_fake_phone(item.get("to_phone"))
            ):
                item["status"] = "skipped"
                item["skip_reason"] = "placeholder_contact"
                _save_queue(queue_path, queue)
            continue
        when = datetime.fromisoformat(item["scheduled_at"])
        if when.tzinfo is None:
            when = when.replace(tzinfo=ZoneInfo("America/New_York"))
        if when.astimezone(ZoneInfo("UTC")) > now:
            continue
        to = item["to_email"]
        ok, skip_reason = _verify_recipient(to)
        if not ok:
            item["status"] = "skipped"
            item["skip_reason"] = skip_reason
            console.print(f"[yellow]Skipped[/yellow] {to}: {skip_reason}")
            if not dry_run:
                _save_queue(queue_path, queue)
            continue
        if dry_run:
            console.print(f"[yellow]Would send[/yellow] → {to}")
            sent += 1
            continue

        item["status"] = "sending"
        item["send_attempted_at"] = now.isoformat()
        _save_queue(queue_path, queue)

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
            item["status"] = "failed"
            item["error"] = str(result.get("error") or "send failed")
            console.print(f"[red]Failed[/red] {to}: {item['error']}")
        else:
            item["status"] = "sent"
            item["sent_at"] = datetime.now(ZoneInfo("UTC")).isoformat()
            console.print(f"[green]Sent[/green] → {to}")
            sent += 1
        _save_queue(queue_path, queue)

    return sent
