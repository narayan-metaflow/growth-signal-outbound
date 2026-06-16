import json
import os
from pathlib import Path

from composio import Composio
from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
GMAIL_TOOLKIT_VERSION = "00000000_00"


def get_composio() -> Composio:
    key = os.environ.get("COMPOSIO_API_KEY")
    if not key:
        raise RuntimeError(
            "COMPOSIO_API_KEY not set. Add it to Cursor Cloud Agent secrets "
            "(Dashboard → Cloud Agents → Secrets)."
        )
    return Composio(
        api_key=key,
        toolkit_versions={"gmail": GMAIL_TOOLKIT_VERSION},
    )


def get_user_id() -> str:
    if os.environ.get("COMPOSIO_USER_ID"):
        return os.environ["COMPOSIO_USER_ID"]
    cfg = ROOT / "config" / "composio.json"
    if cfg.exists():
        return json.loads(cfg.read_text()).get("user_id", "")
    return ""
