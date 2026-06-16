import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "icp.json"
OUTPUT_DIR = ROOT / "output"
# Committed at repo root so cloud agents find them after git clone
QUEUE_FILE = ROOT / "send_queue.json"
OUTREACH_FILE = ROOT / "outreach_drafts.json"


def load_icp() -> dict:
    with open(CONFIG_PATH) as f:
        return json.load(f)
