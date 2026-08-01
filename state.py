"""
Tracks which transfer ids have already been posted, so a run only considers
transfers it hasn't posted before. Unlike an incremental "last seen id"
cursor, Transfermarkt's season page always lists every transfer for the
season, so each run simply re-scrapes it all and filters out anything in
this set. The state file is committed back to the repo by the GitHub
Actions workflow after each run.
"""
import json
import os

import config


def load_posted_ids() -> set[int]:
    if not os.path.exists(config.STATE_FILE):
        return set()
    with open(config.STATE_FILE, "r") as f:
        data = json.load(f)
    return set(data.get("posted_transfer_ids", []))


def save_posted_ids(posted_ids: set[int]) -> None:
    with open(config.STATE_FILE, "w") as f:
        json.dump({"posted_transfer_ids": sorted(posted_ids)}, f, indent=2)
