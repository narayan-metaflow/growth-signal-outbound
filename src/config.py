import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "icp.json"
OUTPUT_DIR = ROOT / "output"


def load_icp() -> dict:
    with open(CONFIG_PATH) as f:
        return json.load(f)
