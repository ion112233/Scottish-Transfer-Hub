"""
Finds a free-to-use photo of a player, for use as the video background,
from Wikimedia Commons - the only source used here, because Commons hosts
exclusively freely-licensed media (CC0/CC-BY/CC-BY-SA), unlike a generic
image search which would mostly surface copyrighted press agency photos
(Getty, PA Images, etc.) that can't legally go on a public YouTube channel.

Commons' full-text search alone isn't a reliable identity match though -
e.g. searching "Nicolas Kühn" (the Celtic winger) also surfaces photos of
Nicola Kuhn, an unrelated tennis player, purely on name similarity. Commons'
own convention of filing every photo of a specific person under a category
matching their name is what actually disambiguates this: a candidate is
only accepted if it carries a category matching the player's name, which is
a much stronger identity signal than the search match itself.

Returns None (video_gen then falls back to its default background) when no
suitable free, identity-confirmed photo can be found - common for
lower-profile squad players who have no Commons coverage at all.
"""
import re
import time
import unicodedata

import requests

API_URL = "https://commons.wikimedia.org/w/api.php"
HEADERS = {"User-Agent": "TransferWebScrapper/1.0 (github.com/ion112233/Transfer-Web-Scrapper)"}
REQUEST_TIMEOUT = 20

ALLOWED_LICENSES = {
    "cc0", "public domain",
    "cc by 2.0", "cc by 3.0", "cc by 4.0",
    "cc by-sa 2.0", "cc by-sa 3.0", "cc by-sa 4.0",
}
MIN_DIMENSION = 500

# A candidate must show positive evidence of being an actual match/training
# photo - a fixture-style category (team names joined by "v"/"vs", or a
# scoreline like "(6-4)") or an explicit open-practice/training/friendly
# category - to be used at all. Merely mentioning a tournament name (e.g. a
# ceremonial "national team meets the Prime Minister after the World Cup"
# photo, which does carry a "2022 FIFA World Cup" category) is not enough,
# so ceremonial/political terms are hard-blocked regardless of that.
_FIXTURE_RE = re.compile(r"\bvs?\.?\b", re.IGNORECASE)
_SCORELINE_RE = re.compile(r"\(\d+[-–]\d+\)")
ACTION_CONTEXT_TERMS = ("open practice", "training session", "training camp",
                         "friendly match", "warm-up", "warmup")
BLOCKED_TERMS = ("prime minister", "president", "official residence", "award",
                  "ceremony", "press conference", "state visit", "parliament",
                  "minister", "embassy", "government", "national assembly")


def _normalize(name: str) -> str:
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _get(params: dict) -> dict:
    for attempt in range(4):
        resp = requests.get(API_URL, params=params, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        if resp.status_code == 429:
            time.sleep(2 ** attempt)
            continue
        resp.raise_for_status()
        return resp.json()
    resp.raise_for_status()
    return {}


def _search_candidates(player_name: str, limit: int = 15) -> list[dict]:
    data = _get({
        "action": "query", "generator": "search", "gsrnamespace": 6,
        "gsrsearch": player_name, "gsrlimit": limit, "prop": "imageinfo",
        "iiprop": "url|size|mime|extmetadata", "format": "json",
    })
    return list(data.get("query", {}).get("pages", {}).values())


def _categories_for_titles(titles: list[str]) -> dict[str, list[str]]:
    """
    Batched request(s) for every candidate's categories, rather than one
    request each. cllimit caps the total categories returned *across the
    whole batch*, not per title, so a handful of heavily-categorized photos
    can silently starve the rest - loop on the continuation token until the
    API reports there's nothing left, merging as we go.
    """
    if not titles:
        return {}
    result: dict[str, list[str]] = {t: [] for t in titles}
    params = {
        "action": "query", "titles": "|".join(titles), "prop": "categories",
        "cllimit": 50, "format": "json",
    }
    while True:
        data = _get(params)
        for p in data.get("query", {}).get("pages", {}).values():
            result.setdefault(p["title"], [])
            result[p["title"]].extend(
                c["title"].removeprefix("Category:") for c in p.get("categories", [])
            )
        cont = data.get("continue")
        if not cont:
            break
        params = {**params, **cont}
    return result


def _matches_player(category: str, player_norm: str) -> bool:
    cat_norm = _normalize(category)
    return bool(cat_norm) and (player_norm == cat_norm or (len(player_norm) > 5 and player_norm in cat_norm))


def _is_match_action_photo(title: str, categories: list[str]) -> bool:
    text = (title + " " + " ".join(categories)).lower()
    if any(term in text for term in BLOCKED_TERMS):
        return False
    if _FIXTURE_RE.search(text) or _SCORELINE_RE.search(text):
        return True
    return any(term in text for term in ACTION_CONTEXT_TERMS)


def _score(info: dict, categories: list[str]) -> float:
    width, height = info.get("width", 0), info.get("height", 0)
    score = min(1.0, max(width, height) / 3000)
    if width and height and 0.6 <= width / height <= 1.8:
        score += 0.2  # not an awkwardly narrow crop
    return score


def find_best_photo(player_name: str) -> dict | None:
    """
    Returns {title, url, width, height, license, artist} for the best
    identity-confirmed, freely-licensed photo found, or None.
    """
    player_norm = _normalize(player_name)
    if not player_norm:
        return None

    prefiltered = []
    for page in _search_candidates(player_name):
        info = (page.get("imageinfo") or [{}])[0]
        if not info or not str(info.get("mime", "")).startswith("image/"):
            continue
        if min(info.get("width", 0), info.get("height", 0)) < MIN_DIMENSION:
            continue
        license_name = (info.get("extmetadata") or {}).get("LicenseShortName", {}).get("value", "")
        if license_name.strip().lower() not in ALLOWED_LICENSES:
            continue
        prefiltered.append((page, info))

    categories_by_title = _categories_for_titles([p["title"] for p, _ in prefiltered])

    candidates = []
    for page, info in prefiltered:
        categories = categories_by_title.get(page["title"], [])
        if not any(_matches_player(c, player_norm) for c in categories):
            continue  # can't confirm this photo is actually of our player
        if not _is_match_action_photo(page["title"], categories):
            continue  # e.g. a ceremonial/press photo rather than match action
        candidates.append((page, info, categories))

    if not candidates:
        return None

    best_page, best_info, best_categories = max(candidates, key=lambda c: _score(c[1], c[2]))
    extmeta = best_info.get("extmetadata") or {}
    return {
        "title": best_page["title"],
        "url": best_info["url"],
        "width": best_info["width"],
        "height": best_info["height"],
        "license": extmeta.get("LicenseShortName", {}).get("value", "Unknown license"),
        "artist": re.sub(r"<[^>]+>", "", extmeta.get("Artist", {}).get("value", "Unknown")).strip(),
    }
