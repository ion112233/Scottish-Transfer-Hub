"""
Thin wrapper around the SportMonks Football API v3 transfers endpoints.

Docs: https://docs.sportmonks.com/v3/endpoints-and-entities/endpoints/transfers
"""
import requests
import config

session = requests.Session()


def _get(path: str, params: dict | None = None) -> dict:
    params = dict(params or {})
    params["api_token"] = config.SPORTMONKS_API_TOKEN
    url = f"{config.SPORTMONKS_BASE_URL}{path}"
    resp = session.get(url, params=params, timeout=30)
    if not resp.ok:
        raise requests.exceptions.HTTPError(
            f"{resp.status_code} error for {resp.url}: {resp.text}", response=resp
        )
    return resp.json()


def _fetch_transfers_page(start_date: str, end_date: str, include: str, per_page: int) -> list[dict]:
    transfers = []
    page = 1
    while True:
        params = {"include": include, "per_page": per_page, "page": page}
        data = _get(f"/transfers/between/{start_date}/{end_date}", params)
        transfers.extend(data.get("data", []))
        if not data.get("pagination", {}).get("has_more"):
            break
        page += 1
    return transfers


def get_transfers_between(start_date: str, end_date: str, per_page: int = 50) -> list[dict]:
    """
    Returns all transfers between start_date and end_date (YYYY-MM-DD,
    inclusive), enriched with player + team names/images/leagues.
    SportMonks caps this endpoint at a 31-day range, 50 results per page,
    and 1 nested include per request - so fromTeam's and toTeam's active
    seasons (needed to know each team's league) can't be requested
    together. This fetches the range twice, once per side, and merges
    the results by transfer id.
    """
    from_pass = _fetch_transfers_page(
        start_date, end_date, "player;fromTeam.activeSeasons;toTeam;type", per_page
    )
    to_pass = _fetch_transfers_page(
        start_date, end_date, "player;fromTeam;toTeam.activeSeasons;type", per_page
    )
    to_pass_by_id = {t["id"]: t for t in to_pass}
    for t in from_pass:
        other = to_pass_by_id.get(t["id"])
        if other:
            t["toTeam"] = other.get("toTeam", t.get("toTeam"))
    return from_pass


def filter_scottish(transfers: list[dict]) -> list[dict]:
    """
    Keep only transfers involving a team that plays in one of the
    configured Scottish league IDs. SportMonks doesn't put a league_id
    directly on a team - it only shows up on that team's active seasons
    (hence the fromTeam.activeSeasons / toTeam.activeSeasons includes).
    """
    if not config.SCOTTISH_LEAGUE_IDS:
        return transfers

    relevant = []
    for t in transfers:
        from_team = t.get("fromTeam") or {}
        to_team = t.get("toTeam") or {}
        league_ids = set()
        for team in (from_team, to_team):
            for season in team.get("activeSeasons") or []:
                lid = season.get("league_id")
                if lid:
                    league_ids.add(lid)
        if league_ids & set(config.SCOTTISH_LEAGUE_IDS):
            relevant.append(t)
    return relevant
