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
    resp.raise_for_status()
    return resp.json()


def get_latest_transfers(id_after: int | None = None, per_page: int = 50) -> list[dict]:
    """
    Returns recent transfers, enriched with player + team names/images.
    If id_after is given, only transfers with a higher id are returned
    (SportMonks' idAfter static filter is designed for exactly this kind
    of incremental polling).
    """
    params = {
        "include": "player;fromTeam;toTeam;type",
        "per_page": per_page,
        "order": "desc",
    }
    if id_after is not None:
        params["filters"] = f"idAfter:{id_after}"

    data = _get("/transfers", params)
    return data.get("data", [])


def filter_scottish(transfers: list[dict]) -> list[dict]:
    """
    Keep only transfers involving a team that plays in one of the
    configured Scottish league IDs. SportMonks doesn't tag a transfer
    with a league directly, so we check the participating teams.
    """
    if not config.SCOTTISH_LEAGUE_IDS:
        return transfers

    relevant = []
    for t in transfers:
        from_team = t.get("fromTeam") or {}
        to_team = t.get("toTeam") or {}
        league_ids = set()
        for team in (from_team, to_team):
            lid = team.get("league_id") or team.get("current_league_id")
            if lid:
                league_ids.add(lid)
        if league_ids & set(config.SCOTTISH_LEAGUE_IDS):
            relevant.append(t)
    return relevant
