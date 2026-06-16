"""Create Gmail drafts or send queued emails via Gmail API."""

from __future__ import annotations

import base64
import json
import os
from email.mime.text import MIMEText
from pathlib import Path

from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from rich.console import Console

from src.config import OUTPUT_DIR

load_dotenv()
console = Console()

ROOT = Path(__file__).resolve().parent.parent
CREDS_FILE = ROOT / "credentials.json"
TOKEN_FILE = ROOT / "token.json"
SCOPES = [
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.send",
]


def _service():
    creds = None
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CREDS_FILE.exists():
                raise RuntimeError(
                    "Missing credentials.json — see Gmail setup in README or run setup below:\n"
                    "1. Google Cloud Console → APIs → enable Gmail API\n"
                    "2. Create OAuth Desktop client → download as credentials.json\n"
                    "3. Place at growth-signal-outbound/credentials.json"
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDS_FILE), SCOPES)
            creds = flow.run_local_server(port=0)
        TOKEN_FILE.write_text(creds.to_json())
    return build("gmail", "v1", credentials=creds)


def _message(to: str, subject: str, body: str) -> dict:
    msg = MIMEText(body)
    msg["to"] = to
    msg["subject"] = subject
    sender = os.environ.get("GMAIL_FROM")
    if sender:
        msg["from"] = sender
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    return {"raw": raw}


def create_drafts(queue_path: Path | None = None) -> list[dict]:
    """Push queue items to Gmail as drafts — schedule send manually in Gmail UI."""
    queue_path = queue_path or OUTPUT_DIR / "send_queue.json"
    queue = json.loads(queue_path.read_text())
    svc = _service()
    results = []

    for item in queue:
        if item.get("status") == "draft_created":
            continue
        to = item.get("to_email")
        if not to:
            continue
        draft = svc.users().drafts().create(
            userId="me",
            body={"message": _message(to, item["subject"], item["body"])},
        ).execute()
        item["status"] = "draft_created"
        item["gmail_draft_id"] = draft.get("id")
        results.append(item)
        console.print(f"[green]Draft[/green] → {to} ({item['company']})")

    queue_path.write_text(json.dumps(queue, indent=2))
    console.print(f"\n{len(results)} drafts in Gmail. Open Gmail → Drafts → open each → Schedule send.")
    return results


def send_due(queue_path: Path | None = None, *, dry_run: bool = False) -> int:
    """Send queue items whose scheduled_at has passed."""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    queue_path = queue_path or OUTPUT_DIR / "send_queue.json"
    queue = json.loads(queue_path.read_text())
    now = datetime.now(ZoneInfo("UTC"))
    svc = _service() if not dry_run else None
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
            console.print(f"[yellow]Would send[/yellow] → {to} ({item['company']})")
        else:
            svc.users().messages().send(
                userId="me", body=_message(to, item["subject"], item["body"])
            ).execute()
            item["status"] = "sent"
            console.print(f"[green]Sent[/green] → {to}")
        sent += 1

    if not dry_run:
        queue_path.write_text(json.dumps(queue, indent=2))
    return sent
