"""Filter hallucinated / placeholder contact data from scraper output."""

import re

FAKE_NAMES = {
    "john doe", "jane doe", "john smith", "jane smith",
    "not specified", "not provided", "n/a", "unknown", "none",
    "cmo name placeholder",
}
FAKE_EMAIL_DOMAINS = {"greenhouse.io", "lever.co", "ashbyhq.com", "example.com"}
FAKE_PHONE_PATTERN = re.compile(r"^(\+?1?[-.\s]?)?(123[-.\s]?456[-.\s]?7890|000|111)")


def is_fake_name(name: str | None) -> bool:
    if not name:
        return True
    return name.strip().lower() in FAKE_NAMES or "placeholder" in name.lower()


def is_fake_email(email: str | None) -> bool:
    if not email:
        return True
    email = email.lower().strip()
    if "@" not in email:
        return True
    local, domain = email.split("@", 1)
    if domain in FAKE_EMAIL_DOMAINS or "example" in domain:
        return True
    if local in {"johndoe", "janedoe", "jane.doe", "john.smith", "test", "info"}:
        return False  # info@ is ok for general contact
    if "johndoe" in local or "janedoe" in local or local == "john.smith":
        return True
    return False


def is_fake_phone(phone: str | None) -> bool:
    if not phone:
        return True
    return bool(FAKE_PHONE_PATTERN.match(phone.replace(" ", "")))


def clean_contact(contact: dict | None) -> dict | None:
    if not contact:
        return None
    name = None if is_fake_name(contact.get("name")) else contact.get("name")
    email = None if is_fake_email(contact.get("email")) else contact.get("email")
    phone = None if is_fake_phone(contact.get("phone")) else contact.get("phone")
    if not any([name, email, phone]):
        return None
    return {**contact, "name": name, "email": email, "phone": phone}


def clean_lead(lead: dict) -> dict:
    lead = dict(lead)
    lead["contact"] = clean_contact(lead.get("contact"))
    if is_fake_email(lead.get("general_email")):
        lead["general_email"] = None
    if is_fake_phone(lead.get("general_phone")):
        lead["general_phone"] = None
    lead["all_contacts"] = [
        c for c in (lead.get("all_contacts") or [])
        if clean_contact(c)
    ]
    return lead
