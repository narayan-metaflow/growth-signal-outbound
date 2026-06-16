import os

from dotenv import load_dotenv
from firecrawl import Firecrawl

load_dotenv()


def get_client() -> Firecrawl:
    key = os.environ.get("FIRECRAWL_API_KEY")
    if not key:
        raise RuntimeError("Set FIRECRAWL_API_KEY in .env")
    return Firecrawl(api_key=key)
