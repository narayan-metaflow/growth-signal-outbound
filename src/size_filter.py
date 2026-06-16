"""Filter leads by company size (max 500 employees)."""

from __future__ import annotations

import json
import re
from pathlib import Path

from firecrawl.v2.types import JsonFormat
from rich.console import Console
from rich.progress import track

from src.config import OUTPUT_DIR, load_icp
from src.firecrawl_client import get_client

console = Console()

SIZE_SCHEMA = {
    "type": "object",
    "properties": {
        "employee_count": {"type": "integer"},
        "employee_range": {"type": "string"},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
        "source_snippet": {"type": "string"},
    },
}

SIZE_PROMPT = (
    "Find the company's employee count or size range. "
    "Return the best numeric estimate as employee_count. "
    "Use confidence high only if a specific number is stated."
)


def _parse_count(text: str) -> int | None:
    if not text:
        return None
    lower = text.lower()
    if not any(k in lower for k in ("employee", "people", "team", "staff", "headcount", "workforce")):
        return None
    text = lower.replace(",", "")
    m = re.search(r"(\d+)\s*[-–]\s*(\d+)\s*(?:employees|people|staff)", text)
    if m:
        return int(m.group(2))
    m = re.search(r"(\d+)\+?\s*(?:employees|people|staff)", text)
    if m:
        return int(m.group(1))
    return None


def _lookup_size(client, company: str) -> dict:
    query = f'"{company}" employees company size'
    try:
        result = client.search(query, limit=3)
        snippets = []
        if hasattr(result, "model_dump"):
            data = result.model_dump()
        else:
            data = result if isinstance(result, dict) else {}
        for item in (data.get("web") or data.get("data", {}).get("web") or []):
            snippets.append(item.get("description") or item.get("snippet") or "")

        combined = " ".join(snippets)
        parsed = _parse_count(combined)
        if parsed:
            return {
                "employee_count": parsed,
                "confidence": "medium",
                "source_snippet": combined[:300],
            }
    except Exception:
        pass

    # Fallback: scrape first search result about page if we have website
    return {"employee_count": None, "confidence": "low", "source_snippet": ""}


def _lookup_size_from_website(client, website: str) -> dict:
    if not website:
        return {"employee_count": None, "confidence": "low"}
    url = website if website.startswith("http") else f"https://{website}"
    try:
        doc = client.scrape(
            url,
            formats=[
                JsonFormat(type="json", prompt=SIZE_PROMPT, schema=SIZE_SCHEMA)
            ],
            wait_for=5000,
        )
        data = doc.json if hasattr(doc, "json") else {}
        if data.get("employee_count"):
            return data
    except Exception:
        pass
    return {"employee_count": None, "confidence": "low"}


def filter_by_size(input_path: Path | None = None, save: bool = True) -> list[dict]:
    icp = load_icp()
    max_emp = icp["max_employees"]
    client = get_client()
    input_path = input_path or OUTPUT_DIR / "scraped_jobs.json"
    jobs = json.loads(input_path.read_text())
    qualified: list[dict] = []
    rejected: list[dict] = []

    for job in track(jobs, description="Checking company size"):
        if job.get("error"):
            rejected.append({**job, "reject_reason": "scrape_failed"})
            continue

        mentioned = _parse_count(job.get("employee_count_mentioned") or "")
        if mentioned and mentioned <= max_emp:
            job["employee_count"] = mentioned
            job["size_confidence"] = "high"
            qualified.append(job)
            continue
        if mentioned and mentioned > max_emp:
            rejected.append({**job, "employee_count": mentioned, "reject_reason": "too_large"})
            continue

        company = job.get("company") or ""
        size = _lookup_size(client, company)
        if not size.get("employee_count") and job.get("company_website"):
            size = _lookup_size_from_website(client, job["company_website"])

        count = size.get("employee_count")
        job["employee_count"] = count
        job["size_confidence"] = size.get("confidence", "low")

        if count is None:
            job["needs_review"] = True
            qualified.append(job)
        elif count <= max_emp:
            if count >= max_emp * 0.8 and job.get("size_confidence") != "high":
                job["needs_review"] = True
            qualified.append(job)
        else:
            rejected.append({**job, "reject_reason": "too_large"})

    console.print(f"[green]Qualified: {len(qualified)}[/green] | [red]Rejected: {len(rejected)}[/red]")

    if save:
        OUTPUT_DIR.mkdir(exist_ok=True)
        (OUTPUT_DIR / "qualified_leads.json").write_text(json.dumps(qualified, indent=2))
        (OUTPUT_DIR / "rejected_leads.json").write_text(json.dumps(rejected, indent=2))

    return qualified


if __name__ == "__main__":
    filter_by_size()
