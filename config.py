"""
Central configuration. All values come from environment variables so that
nothing sensitive is hard-coded. In GitHub Actions these are injected from
repository secrets (see .github/workflows/hourly-transfers.yml).
"""
import os

# --- SportMonks ---
SPORTMONKS_API_TOKEN = os.environ["SPORTMONKS_API_TOKEN"]
SPORTMONKS_BASE_URL = "https://api.sportmonks.com/v3/football"

# League IDs to track. Defaults to the Scottish leagues available on the
# SportMonks free plan. You can find/confirm IDs at:
# https://api.sportmonks.com/v3/football/leagues?api_token=YOUR_TOKEN&search=scottish
# (or via https://docs.sportmonks.com/football/api-basics/id-finder)
SCOTTISH_LEAGUE_IDS = [
    int(x) for x in os.environ.get(
        "SCOTTISH_LEAGUE_IDS",
        "501,502,503,504",  # Premiership, Championship, League One, League Two (verify/adjust)
    ).split(",")
    if x.strip()
]

# --- YouTube ---
YOUTUBE_CLIENT_ID = os.environ["YOUTUBE_CLIENT_ID"]
YOUTUBE_CLIENT_SECRET = os.environ["YOUTUBE_CLIENT_SECRET"]
YOUTUBE_REFRESH_TOKEN = os.environ["YOUTUBE_REFRESH_TOKEN"]

# --- Misc ---
STATE_FILE = os.environ.get("STATE_FILE", "state.json")
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "output")
MAX_TRANSFERS_PER_RUN = int(os.environ.get("MAX_TRANSFERS_PER_RUN", "3"))
DRY_RUN = os.environ.get("DRY_RUN", "false").lower() == "true"
