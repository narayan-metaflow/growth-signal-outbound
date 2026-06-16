import os

from composio import Composio
from dotenv import load_dotenv

load_dotenv()

DEFAULT_USER_ID = "35cdd829-8871-4432-83bf-4cf4591e09db"
GMAIL_TOOLKIT_VERSION = "00000000_00"


def get_composio() -> Composio:
    key = os.environ.get("COMPOSIO_API_KEY")
    if not key:
        raise RuntimeError("Set COMPOSIO_API_KEY in .env")
    return Composio(
        api_key=key,
        toolkit_versions={"gmail": GMAIL_TOOLKIT_VERSION},
    )


def get_user_id() -> str:
    return os.environ.get("COMPOSIO_USER_ID", DEFAULT_USER_ID)
