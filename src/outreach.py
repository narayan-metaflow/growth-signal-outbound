"""Generate personalized cold outreach drafts from hiring signals."""

from __future__ import annotations

import json
import random
from pathlib import Path

from rich.console import Console

from src.config import OUTPUT_DIR
from src.validators import clean_lead, is_fake_email, is_fake_name, is_fake_phone

console = Console()

# Edit these for your offer
SENDER = {
    "name": "Your Name",
    "company": "Your Company",
    "value_prop": "help growth teams scale paid + lifecycle without adding headcount",
}


def _first_name(full: str | None) -> str | None:
    if not full:
        return None
    cleaned = full.strip()
    if cleaned.lower() in {"unknown", "not provided", "n/a", "none", ""}:
        return None
    return cleaned.split()[0]


def _role_bucket(role: str) -> str:
    r = role.lower()
    if "cmo" in r or "chief marketing" in r:
        return "cmo"
    if "head" in r:
        return "head"
    return "manager"


def _has_any(text: str, keywords: tuple[str, ...]) -> bool:
    t = text.lower()
    return any(k in t for k in keywords)


def _context_bits(lead: dict) -> dict:
    role = lead.get("job_title") or "growth role"
    reqs = " ".join(lead.get("key_requirements") or []).lower()
    desc = (lead.get("company_description") or "").lower()
    blob = f"{reqs} {desc}"

    return {
        "role": role,
        "bucket": _role_bucket(role),
        "paid_heavy": _has_any(blob, ("paid", "meta", "google ads", "acquisition", "performance")),
        "plg": _has_any(blob, ("plg", "self-serve", "product-led")),
        "ai_angle": _has_any(blob, ("ai", "martech", "automation")),
        "budget_heavy": _has_any(blob, ("seven figure", "7-figure", "million", "budget")),
        "remote": _has_any(
            (lead.get("remote_status") or "").lower(),
            ("remote", "anywhere", "distributed"),
        ),
    }


def _subjects(company: str, ctx: dict) -> list[str]:
    role = ctx["role"]
    base = [
        f"quick question on the {role} hire",
        f"{company} — before the new hire starts",
        f"who owns growth in the meantime?",
    ]
    if ctx["paid_heavy"]:
        base.append("paid + the new growth hire")
    if ctx["plg"]:
        base.append("PLG + growth leadership")
    if ctx["bucket"] == "cmo":
        base.append("marketing while you search for a CMO")
    return base


def _bodies(first: str | None, company: str, ctx: dict) -> list[str]:
    o = f"Hi {first},\n\n" if first else "Hi,\n\n"
    role = ctx["role"]
    v = SENDER["value_prop"]

    templates: list[str] = []

    if ctx["bucket"] == "cmo":
        templates.extend([
            f"""{o}You're filling a CMO seat — but marketing still has to run every day until someone's in.

Who's owning pipeline and priorities in the meantime?

We {v}. The 60 days before a leader starts usually go one of two ways — curious which way {company} is set up for.

Open to 15 minutes to compare notes?""",

            f"""{o}CMO search is underway at {company}. One thing I see often: the quarter between "we need a leader" and "they're ramped" is when momentum quietly slips.

Not a people problem — an ownership gap.

We {v}. Happy to share what's worked for similar teams if a short call would help.""",
        ])

    if ctx["bucket"] == "head":
        templates.extend([
            f"""{o}You're bringing on a {role} at {company}. Quick question — will they walk into a clear stack and experiments in flight, or a few months of untangling first?

We {v}. The teams that move fastest usually sort that out before day one.

Worth 15 minutes to talk through it?""",

            f"""{o}New {role} at {company}. The hire matters — but so does what they inherit on day one.

Curious if that's already mapped out, or still taking shape.

We {v}. Open to a brief call if it'd be useful.""",
        ])

    if ctx["paid_heavy"]:
        templates.append(
            f"""{o}Big paid program + a new {role} at the same time — that's a lot to coordinate.

How are you thinking about what paid owns now vs. what changes once the new lead is in?

We {v}. 15 minutes if you'd find that conversation helpful."""
        )

    if ctx["plg"]:
        templates.append(
            f"""{o}PLG company, new {role} — usually means the product works and now it's about scaling what got you here.

Sometimes the real gap isn't acquisition. It's a step or two downstream.

We {v}. Curious if that's on your radar at {company} — open to a quick call?"""
        )

    if ctx["ai_angle"]:
        templates.append(
            f"""{o}You're building out growth leadership at {company} while the stack keeps evolving — AI, tooling, the works.

What does "good" look like in the next 60 days, before the new {role} is fully settled?

We {v}. Happy to compare notes if that's useful."""
        )

    templates.extend([
        f"""{o}You're hiring a {role} at {company}. The window before they start often matters as much as the hire itself.

Curious how you're handling that stretch.

We {v}. 15 minutes if a quick conversation would help.""",

        f"""{o}Growth leadership is clearly a priority at {company} right now.

One question — is the bottleneck people, process, or the foundation underneath? Most teams your size are juggling all three.

We {v}. Open to a short call if you'd like to talk it through.""",

        f"""{o}Quick note — {company} is building out the growth function, and that in-between period before a new {role} starts is where I've seen the most variance across teams.

Some come out ahead. Some lose a quarter.

We {v}. Worth 15 minutes to see where you land?""",
    ])

    return templates


def draft_email(lead: dict, *, seed: int | None = None) -> dict:
    lead = clean_lead(lead)
    contact = lead.get("contact") or {}
    name = contact.get("name") or lead.get("hiring_manager_name")
    email = contact.get("email") or lead.get("general_email")
    phone = contact.get("phone") or lead.get("general_phone")
    if is_fake_name(name):
        name = None
    if is_fake_email(email):
        email = None
    if is_fake_phone(phone):
        phone = None

    first = _first_name(name)
    company = lead.get("company") or "your team"
    ctx = _context_bits(lead)

    rng = random.Random(seed if seed is not None else hash(lead.get("source_url", company)))
    subject = rng.choice(_subjects(company, ctx))
    body = rng.choice(_bodies(first, company, ctx))
    body = f"{body.rstrip()}\n\nBest,\n{SENDER['name']}"

    return {
        "to_name": name,
        "to_email": email,
        "to_phone": phone,
        "subject": subject,
        "body": body,
        "company": company,
        "signal": ctx["role"],
        "source_url": lead.get("source_url"),
    }


def generate_outreach(input_path: Path | None = None, save: bool = True) -> list[dict]:
    input_path = input_path or OUTPUT_DIR / "enriched_leads.json"
    leads = json.loads(input_path.read_text())
    drafts = []

    for lead in leads:
        draft = draft_email(lead)
        draft["needs_review"] = lead.get("needs_review", False)
        draft["employee_count"] = lead.get("employee_count")
        drafts.append(draft)

    if save:
        OUTPUT_DIR.mkdir(exist_ok=True)
        out_json = OUTPUT_DIR / "outreach_drafts.json"
        out_json.write_text(json.dumps(drafts, indent=2))

        out_md = OUTPUT_DIR / "outreach_drafts.md"
        lines = []
        for i, d in enumerate(drafts, 1):
            lines.append(f"## {i}. {d['company']} — {d['signal']}\n")
            if d.get("needs_review"):
                lines.append("*⚠ Company size unverified — manual review recommended*\n")
            lines.append(f"**To:** {d.get('to_name') or 'Unknown'} ({d.get('to_email') or 'no email'})  ")
            if d.get("to_phone"):
                lines.append(f"| **Phone:** {d['to_phone']}  ")
            lines.append(f"\n**Subject:** {d['subject']}\n\n{d['body']}\n\n---\n")
        out_md.write_text("\n".join(lines))
        console.print(f"Saved → {out_json} and {out_md}")

    return drafts


if __name__ == "__main__":
    generate_outreach()
