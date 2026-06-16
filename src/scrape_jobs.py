"""Scrape job posts and extract structured hiring signal data."""

from __future__ import annotations

import json
from pathlib import Path

from firecrawl.v2.types import JsonFormat
from rich.console import Console
from rich.progress import track

from src.config import OUTPUT_DIR
from src.firecrawl_client import get_client

console = Console()

JOB_DETAIL_SCHEMA = {
    "type": "object",
    "properties": {
        "company": {"type": "string"},
        "job_title": {"type": "string"},
        "location": {"type": "string"},
        "remote_status": {"type": "string"},
        "salary": {"type": "string"},
        "company_website": {"type": "string"},
        "hiring_manager_name": {"type": "string"},
        "hiring_manager_title": {"type": "string"},
        "key_requirements": {"type": "array", "items": {"type": "string"}},
        "company_description": {"type": "string"},
        "employee_count_mentioned": {"type": "string"},
    },
    "required": ["company", "job_title"],
}

SCRAPE_PROMPT = (
    "Extract hiring details from this job posting. "
    "Include company website if linked. "
    "Note any hiring manager or recruiter named. "
    "Capture employee count or company size if mentioned in the post."
)


def _extract_json(doc) -> dict:
    if hasattr(doc, "json"):
        return doc.json or {}
    if hasattr(doc, "model_dump"):
        data = doc.model_dump()
        return data.get("json") or data.get("data", {}).get("json") or {}
    if isinstance(doc, dict):
        return doc.get("json") or doc.get("data", {}).get("json") or {}
    return {}


def scrape_jobs(input_path: Path | None = None, save: bool = True) -> list[dict]:
    client = get_client()
    input_path = input_path or OUTPUT_DIR / "discovered.json"
    discovered = json.loads(input_path.read_text())
    scraped: list[dict] = []

    for item in track(discovered, description="Scraping jobs"):
        url = item["url"]
        try:
            doc = client.scrape(
                url,
                formats=[
                    JsonFormat(
                        type="json",
                        prompt=SCRAPE_PROMPT,
                        schema=JOB_DETAIL_SCHEMA,
                    )
                ],
                wait_for=5000,
                only_main_content=True,
            )
            detail = _extract_json(doc)
            if not detail.get("company"):
                detail["company"] = item.get("company") or ""
            scraped.append({"source_url": url, "search_title": item.get("title"), **detail})
        except Exception as exc:
            console.print(f"[red]Failed {url}:[/red] {exc}")
            scraped.append({"source_url": url, "error": str(exc)})

    if save:
        OUTPUT_DIR.mkdir(exist_ok=True)
        out = OUTPUT_DIR / "scraped_jobs.json"
        out.write_text(json.dumps(scraped, indent=2))
        console.print(f"Saved → {out}")
    return scraped


if __name__ == "__main__":
    scrape_jobs()
