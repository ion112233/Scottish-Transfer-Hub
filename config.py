"""
Central configuration. All secrets come from environment variables so that
nothing sensitive is hard-coded. In GitHub Actions these are injected from
repository secrets (see .github/workflows/eight-hourly-transfers.yml).
"""
import os

# --- YouTube ---
YOUTUBE_CLIENT_ID = os.environ["YOUTUBE_CLIENT_ID"]
YOUTUBE_CLIENT_SECRET = os.environ["YOUTUBE_CLIENT_SECRET"]
YOUTUBE_REFRESH_TOKEN = os.environ["YOUTUBE_REFRESH_TOKEN"]

# --- Scraping ---
REQUEST_TIMEOUT = 30
# Override the auto-detected Transfermarkt season id (e.g. "2026" for 26/27)
# if you ever need to force a specific season.
SEASON_ID_OVERRIDE = int(os.environ["SEASON_ID_OVERRIDE"]) if os.environ.get("SEASON_ID_OVERRIDE") else None

# --- Ranking ---
# Scottish Premiership club prominence weights (0-10). Clubs not listed here
# (i.e. any club outside the Premiership - foreign or lower-league) get
# OTHER_CLUB_WEIGHT, since a cross-border move is still newsworthy even if
# the counterpart club isn't one we've weighted individually.
CLUB_WEIGHTS = {
    371: 10,   # Celtic FC
    124: 10,   # Rangers FC
    43: 6,     # Heart of Midlothian FC
    903: 6,    # Hibernian FC
    370: 6,    # Aberdeen FC
    987: 4,    # Motherwell FC
    511: 4,    # Dundee FC
    1519: 4,   # Dundee United FC
    465: 4,    # St. Mirren FC
    2578: 4,   # St. Johnstone FC
    2553: 4,   # Kilmarnock FC
    1191: 4,   # Falkirk FC
}
OTHER_CLUB_WEIGHT = 3

# Hashtags added to each video's description for whichever of these clubs
# are involved (in addition to the static hashtags in main.py), so fans
# actively searching a club's tag are more likely to surface the video.
CLUB_HASHTAGS = {
    371: "#Celtic",
    124: "#Rangers",
    43: "#Hearts",
    903: "#Hibs",
    370: "#Aberdeen",
    987: "#Motherwell",
    511: "#DundeeFC",
    1519: "#DundeeUnited",
    465: "#StMirren",
    2578: "#StJohnstone",
    2553: "#Kilmarnock",
    1191: "#Falkirk",
}

# Score = FEE_WEIGHT*fee_score + MARKET_VALUE_WEIGHT*mv_score + CLUB_WEIGHT*club_score
FEE_WEIGHT = 0.45
MARKET_VALUE_WEIGHT = 0.30
CLUB_WEIGHT = 0.25
FEE_CAP_EUR = 8_000_000       # fee at/above this scores 1.0 on the fee component
MARKET_VALUE_CAP_EUR = 10_000_000

# --- Music ---
# "New Hero in Town" by Kevin MacLeod (incompetech.com), Creative Commons:
# By Attribution 4.0 (creativecommons.org/licenses/by/4.0/). The file lives
# at assets/background_music.mp3 - see README "Background music" for the
# license terms this credit line satisfies.
MUSIC_PATH = os.path.join(os.path.dirname(__file__), "assets", "background_music.mp3")
MUSIC_VOLUME = 0.12  # kept low so it never competes with the voiceover
MUSIC_CREDIT = (
    '"New Hero in Town" by Kevin MacLeod (incompetech.com), '
    "licensed under CC BY 4.0 (creativecommons.org/licenses/by/4.0/)."
)

# --- Reliability ---
RETRY_ATTEMPTS = int(os.environ.get("RETRY_ATTEMPTS", "3"))
RETRY_BASE_DELAY = float(os.environ.get("RETRY_BASE_DELAY", "3"))
# All optional - if unset, notify.py just logs and skips sending.
GMAIL_ADDRESS = os.environ.get("GMAIL_ADDRESS")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD")
NOTIFY_EMAIL = os.environ.get("NOTIFY_EMAIL") or GMAIL_ADDRESS

# --- Misc ---
STATE_FILE = os.environ.get("STATE_FILE", "state.json")
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "output")
MAX_TRANSFERS_PER_RUN = int(os.environ.get("MAX_TRANSFERS_PER_RUN", "2"))
DRY_RUN = os.environ.get("DRY_RUN", "false").lower() == "true"
TTS_VOICE = os.environ.get("TTS_VOICE", "en-GB-RyanNeural")
