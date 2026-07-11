"""
Tracks the highest transfer ID we've already posted, so an hourly run only
picks up genuinely new transfers. The state file is committed back to the
repo by the GitHub Actions workflow after each run.
"""
import json
import os
import config


def load_last_seen_id() -> int | None:
    if not os.path.exists(config.STATE_FILE):
        return None
    with open(config.STATE_FILE, "r") as f:
        data = json.load(f)
    return data.get("last_seen_id")


def save_last_seen_id(transfer_id: int) -> None:
    with open(config.STATE_FILE, "w") as f:
        json.dump({"last_seen_id": transfer_id}, f, indent=2)
