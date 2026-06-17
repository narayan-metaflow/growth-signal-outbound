#!/usr/bin/env python3
"""Run the full growth-signal outbound pipeline."""

import argparse

from rich.console import Console

from src.composio_gmail import (
    connect as composio_connect,
    create_drafts as composio_drafts,
    print_schedule_guide,
    send_due as composio_send,
)
from src.discover import discover
from src.enrich import enrich
from src.gmail_send import create_drafts, send_due
from src.outreach import generate_outreach
from src.schedule_sends import build_queue
from src.scrape_jobs import scrape_jobs
from src.size_filter import filter_by_size

console = Console()

STEPS = {
    "discover": discover,
    "scrape": scrape_jobs,
    "filter": filter_by_size,
    "enrich": enrich,
    "outreach": generate_outreach,
    "schedule": build_queue,
}


def main():
    parser = argparse.ArgumentParser(description="Growth signal outbound pipeline")
    parser.add_argument(
        "step",
        nargs="?",
        choices=["all", "publish", "gmail-drafts", "send", "composio-drafts", "composio-send", "composio-connect", "send-daemon", *STEPS.keys()],
        default="all",
        help="Pipeline step to run (default: all)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of jobs to process (discover/scrape steps)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="For send: show what would send without sending",
    )
    args = parser.parse_args()

    if args.limit and args.step in ("all", "discover"):
        icp = __import__("src.config", fromlist=["load_icp"]).load_icp()
        icp["results_per_query"] = max(1, args.limit // len(icp["search_queries"]))

    if args.step == "all":
        steps = list(STEPS.keys())
    elif args.step == "publish":
        build_queue()
        composio_drafts()
        print_schedule_guide()
        console.print("\n[green]Done.[/green] Schedule each draft in Gmail — do not use composio-send or Cursor automation.")
        return
    elif args.step == "composio-connect":
        composio_connect()
        return
    elif args.step == "composio-drafts":
        build_queue()
        composio_drafts()
        return
    elif args.step == "composio-send":
        n = composio_send(dry_run=args.dry_run)
        console.print(f"{'Would send' if args.dry_run else 'Sent'}: {n}")
        return
    elif args.step == "send-daemon":
        from src.send_daemon import run_daemon
        run_daemon()
        return
    elif args.step == "gmail-drafts":
        build_queue()
        create_drafts()
        return
    elif args.step == "send":
        n = send_due(dry_run=args.dry_run)
        console.print(f"{'Would send' if args.dry_run else 'Sent'}: {n}")
        return
    else:
        steps = [args.step]

    for name in steps:
        console.rule(f"[bold]{name}[/bold]")
        if name == "discover":
            discover()
            if args.limit:
                import json
                from pathlib import Path
                from src.config import OUTPUT_DIR
                p = OUTPUT_DIR / "discovered.json"
                data = json.loads(p.read_text())
                p.write_text(json.dumps(data[: args.limit], indent=2))
        else:
            STEPS[name]()


if __name__ == "__main__":
    main()
