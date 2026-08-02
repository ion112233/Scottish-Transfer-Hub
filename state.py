"""
Tracks every transfer id already seen in some previous scrape, so a run
only ranks transfers that are new since last time - i.e. confirmed roughly
within the last check interval (8h), rather than resurfacing something
from the backlog that's been sitting on Transfermarkt's page for weeks.

Transfermarkt's season page doesn't expose an exact "date confirmed" field
for most transfers (only loan-*end* dates), and fetching each transfer's
own detail page just to get one wouldn't fit the one-request-per-run
scraping etiquette - "new since the last scrape" is used as a practical
stand-in instead.

Every run marks the *entire* current scrape as seen, regardless of
whether a given transfer was actually posted (not enough of the day's
quota to post it) or attempted-and-failed - a transfer only gets one
window of eligibility, matching "only the newest transfers" rather than
carrying a retry backlog forward indefinitely. The state file is
committed back to the repo by the GitHub Actions workflow after each run.
"""
import json
import os

import config


def load_seen_ids() -> set[int]:
    if not os.path.exists(config.STATE_FILE):
        return set()
    with open(config.STATE_FILE, "r") as f:
        data = json.load(f)
    return set(data.get("seen_transfer_ids", []))


def save_seen_ids(seen_ids: set[int]) -> None:
    with open(config.STATE_FILE, "w") as f:
        json.dump({"seen_transfer_ids": sorted(seen_ids)}, f, indent=2)
