import os
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv

load_dotenv()

BASE = "https://api.hunter.io/v2"

TARGET_TITLES = (
    "chief marketing officer",
    "cmo",
    "chief marketing",
    "head of growth",
    "vp of growth",
    "vp growth",
    "vice president of growth",
    "vp marketing",
    "vice president of marketing",
    "director of growth",
    "director of marketing",
    "growth marketing",
)


def _api_key() -> str:
    key = os.environ.get("HUNTER_API_KEY")
    if not key:
        raise RuntimeError("Set HUNTER_API_KEY in .env")
    return key


def domain_from_url(website: str | None) -> str | None:
    if not website:
        return None
    url = website if website.startswith("http") else f"https://{website}"
    host = urlparse(url).netloc.lower().removeprefix("www.")
    if not host or host.endswith(("greenhouse.io", "lever.co", "ashbyhq.com")):
        return None
    return host


def _score_contact(title: str) -> int:
    t = title.lower()
    for i, needle in enumerate(TARGET_TITLES):
        if needle in t:
            return len(TARGET_TITLES) - i
    if any(d in t for d in ("marketing", "growth")):
        return 1
    return 0


def domain_search(domain: str | None = None, company: str | None = None) -> list[dict]:
    params = {
        "api_key": _api_key(),
        "department": "marketing,executive,management",
        "seniority": "executive,senior",
        "limit": 10,
    }
    if domain:
        params["domain"] = domain
    elif company:
        params["company"] = company
    else:
        return []

    resp = requests.get(f"{BASE}/domain-search", params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json().get("data") or {}
    emails = data.get("emails") or []
    out = []
    for e in emails:
        out.append(
            {
                "name": f"{e.get('first_name') or ''} {e.get('last_name') or ''}".strip(),
                "title": e.get("position") or "",
                "email": e.get("value") or "",
                "phone": None,
                "confidence": e.get("confidence"),
                "source": "hunter_domain_search",
            }
        )
    return out


def email_finder(
    domain: str | None = None,
    company: str | None = None,
    *,
    first_name: str,
    last_name: str,
) -> dict | None:
    params = {
        "api_key": _api_key(),
        "first_name": first_name,
        "last_name": last_name,
    }
    if domain:
        params["domain"] = domain
    elif company:
        params["company"] = company
    else:
        return None

    resp = requests.get(f"{BASE}/email-finder", params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json().get("data") or {}
    email = data.get("email")
    if not email:
        return None
    return {
        "name": f"{first_name} {last_name}".strip(),
        "title": data.get("position") or "",
        "email": email,
        "confidence": data.get("score"),
        "source": "hunter_email_finder",
    }


def pick_best_contact(contacts: list[dict]) -> dict | None:
    ranked = []
    for c in contacts:
        if not c.get("email"):
            continue
        score = _score_contact(c.get("title") or "")
        conf = c.get("confidence") or 0
        if isinstance(conf, (int, float)):
            score += min(conf // 20, 3)
        ranked.append((score, c))
    ranked.sort(key=lambda x: x[0], reverse=True)
    return ranked[0][1] if ranked and ranked[0][0] > 0 else None


def find_contact_for_lead(lead: dict) -> tuple[dict | None, list[dict], str | None]:
    """Returns (best_contact, all_contacts, domain)."""
    domain = domain_from_url(lead.get("company_website"))
    company = lead.get("company") or ""

    contacts: list[dict] = []
    if domain or company:
        try:
            contacts.extend(domain_search(domain=domain, company=company if not domain else None))
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 429:
                raise
        except Exception:
            pass

    hm = lead.get("hiring_manager_name") or ""
    if hm and " " in hm.strip():
        parts = hm.strip().split(None, 1)
        try:
            found = email_finder(
                domain=domain,
                company=company if not domain else None,
                first_name=parts[0],
                last_name=parts[1],
            )
            if found:
                contacts.insert(0, found)
        except Exception:
            pass

    best = pick_best_contact(contacts)
    return best, contacts, domain
