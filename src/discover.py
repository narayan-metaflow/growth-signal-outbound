"""Discover hiring signals via Firecrawl search."""

from __future__ import annotations

import json
from pathlib import Path

from rich.console import Console

from src.config import OUTPUT_DIR, load_icp
from src.firecrawl_client import get_client

console = Console()

JOB_SCHEMA = {
    "type": "object",
    "properties": {
        "jobs": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                    "title": {"type": "string"},
                    "company": {"type": "string"},
                    "snippet": {"type": "string"},
                },
                "required": ["url", "title"],
            },
        }
    },
}


def _urls_from_search(result) -> list[dict]:
    """Normalize Firecrawl search response into job URL records."""
    hits: list[dict] = []
    data = result
    if hasattr(result, "model_dump"):
        data = result.model_dump()
    elif hasattr(result, "dict"):
        data = result.dict()

    web = (data or {}).get("web") or (data or {}).get("data", {}).get("web") or []
    for item in web:
        url = item.get("url") or ""
        if not url:
            continue
        if not any(d in url for d in ("greenhouse.io", "lever.co", "ashbyhq.com")):
            continue
        hits.append(
            {
                "url": url,
                "title": item.get("title") or item.get("metadata", {}).get("title", ""),
                "snippet": item.get("description") or item.get("snippet") or "",
                "company": _guess_company(url, item.get("title", "")),
            }
        )
    return hits


def _guess_company(url: str, title: str) -> str:
    if " - " in title:
        parts = title.split(" - ")
        if len(parts) >= 2:
            return parts[0].replace("Job Application for ", "").strip()
    if "lever.co/" in url:
        slug = url.split("lever.co/")[1].split("/")[0]
        return slug.replace("-", " ").title()
    if "greenhouse.io/" in url:
        slug = url.split("greenhouse.io/")[1].split("/")[0]
        return slug.replace("-", " ").title()
    return ""


def discover(save: bool = True) -> list[dict]:
    icp = load_icp()
    client = get_client()
    seen: set[str] = set()
    leads: list[dict] = []

    for query in icp["search_queries"]:
        console.print(f"[cyan]Searching:[/cyan] {query[:80]}...")
        result = client.search(
            query,
            include_domains=icp["search_domains"],
            limit=icp["results_per_query"],
        )
        for hit in _urls_from_search(result):
            if hit["url"] in seen:
                continue
            seen.add(hit["url"])
            leads.append(hit)

    console.print(f"[green]Found {len(leads)} unique job URLs[/green]")
    if save:
        OUTPUT_DIR.mkdir(exist_ok=True)
        out = OUTPUT_DIR / "discovered.json"
        out.write_text(json.dumps(leads, indent=2))
        console.print(f"Saved → {out}")
    return leads


if __name__ == "__main__":
    discover()
