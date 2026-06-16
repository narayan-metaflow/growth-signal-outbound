"""Enrich leads — Hunter.io first, Firecrawl team pages as fallback."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urljoin, urlparse

from firecrawl.v2.types import JsonFormat
from rich.console import Console
from rich.progress import track

from src.config import OUTPUT_DIR
from src.firecrawl_client import get_client
from src.hunter_client import domain_from_url, find_contact_for_lead

console = Console()

CONTACT_SCHEMA = {
    "type": "object",
    "properties": {
        "contacts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "title": {"type": "string"},
                    "email": {"type": "string"},
                    "phone": {"type": "string"},
                },
            },
        },
        "general_email": {"type": "string"},
        "general_phone": {"type": "string"},
    },
}

CONTACT_PROMPT = (
    "Extract marketing leadership: CMO, Head of Growth, VP Marketing. "
    "Include public emails. Skip generic support@ unless nothing else."
)

TARGET_TITLES = (
    "cmo", "chief marketing", "head of growth", "vp growth",
    "vp marketing", "growth marketing", "director of growth", "director of marketing",
)


def _base_url(website: str) -> str | None:
    if not website:
        return None
    url = website if website.startswith("http") else f"https://{website}"
    parsed = urlparse(url)
    if not parsed.netloc:
        return None
    return f"{parsed.scheme}://{parsed.netloc}"


def _candidate_pages(base: str) -> list[str]:
    return [urljoin(base, p) for p in ("/team", "/about", "/leadership", "/contact")]


def _find_website(client, company: str) -> str | None:
    try:
        result = client.search(f'"{company}" official website', limit=3)
        data = result.model_dump() if hasattr(result, "model_dump") else result
        for item in (data.get("web") or []):
            url = item.get("url") or ""
            if any(s in url for s in ("linkedin.com", "glassdoor", "crunchbase", "greenhouse.io", "lever.co")):
                continue
            if url.startswith("http"):
                return url
    except Exception:
        pass
    return None


def _scrape_contacts(client, url: str) -> dict:
    try:
        doc = client.scrape(
            url,
            formats=[JsonFormat(type="json", prompt=CONTACT_PROMPT, schema=CONTACT_SCHEMA)],
            wait_for=5000,
            only_main_content=True,
        )
        return doc.json if hasattr(doc, "json") and doc.json else {}
    except Exception:
        return {}


def _pick_scraped(contacts: list[dict]) -> dict | None:
    ranked = []
    for c in contacts:
        title = (c.get("title") or "").lower()
        score = next((len(TARGET_TITLES) - i for i, t in enumerate(TARGET_TITLES) if t in title), 0)
        if c.get("email"):
            score += 2
        ranked.append((score, c))
    ranked.sort(key=lambda x: x[0], reverse=True)
    return ranked[0][1] if ranked and ranked[0][0] > 0 else None


def enrich(input_path: Path | None = None, save: bool = True, *, use_firecrawl_fallback: bool = True) -> list[dict]:
    input_path = input_path or OUTPUT_DIR / "qualified_leads.json"
    leads = json.loads(input_path.read_text())
    enriched: list[dict] = []
    fc = get_client() if use_firecrawl_fallback else None
    hunter_hits = 0

    for lead in track(leads, description="Enriching (Hunter + fallback)"):
        website = lead.get("company_website")
        if not domain_from_url(website):
            website = website or _find_website(fc, lead.get("company", "")) if fc else website
            lead = {**lead, "company_website": website}

        best, hunter_contacts, domain = find_contact_for_lead(lead)
        source = best.get("source") if best else None
        if best:
            hunter_hits += 1

        scraped: list[dict] = []
        general_email = general_phone = None

        if not best and use_firecrawl_fallback and fc:
            base = _base_url(website) if website else None
            if base:
                for page_url in _candidate_pages(base):
                    data = _scrape_contacts(fc, page_url)
                    scraped.extend(data.get("contacts") or [])
                    general_email = general_email or data.get("general_email")
                    general_phone = general_phone or data.get("general_phone")
                best = _pick_scraped(scraped)
                source = "firecrawl" if best else source

        enriched.append({
            **lead,
            "company_domain": domain,
            "company_website": website or lead.get("company_website"),
            "contact": best,
            "contact_source": source,
            "hunter_contacts": hunter_contacts[:10],
            "scraped_contacts": scraped[:5],
            "general_email": general_email,
            "general_phone": general_phone,
        })

    console.print(f"[green]Hunter matches: {hunter_hits}/{len(leads)}[/green]")

    if save:
        OUTPUT_DIR.mkdir(exist_ok=True)
        (OUTPUT_DIR / "enriched_leads.json").write_text(json.dumps(enriched, indent=2))
        console.print(f"Saved → {OUTPUT_DIR / 'enriched_leads.json'}")

    return enriched


if __name__ == "__main__":
    enrich()
