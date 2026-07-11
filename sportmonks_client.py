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


def get_transfers_between(start_date: str, end_date: str, per_page: int = 50) -> list[dict]:
    """
    Returns all transfers between start_date and end_date (YYYY-MM-DD,
    inclusive), enriched with player + team names/images. SportMonks caps
    this endpoint at a 31-day range and 50 results per page, so this
    paginates until every page has been fetched. Only flat (non-nested)
    includes are used here - this endpoint allows at most 1 nested
    include per request, which isn't enough to also pull each team's
    league (see get_scottish_team_ids for how that's resolved instead).
    """
    transfers = []
    page = 1
    while True:
        params = {
            "include": "player;fromTeam;toTeam;type",
            "per_page": per_page,
            "page": page,
        }
        data = _get(f"/transfers/between/{start_date}/{end_date}", params)
        transfers.extend(data.get("data", []))
        if not data.get("pagination", {}).get("has_more"):
            break
        page += 1
    return transfers


def get_scottish_team_ids() -> set[int]:
    """
    Returns the ids of every team currently playing in one of the
    configured Scottish leagues, by looking up each league's current
    season and then that season's teams. Independent of the transfers
    endpoint, so it isn't subject to its nested-include limit.
    """
    team_ids = set()
    for league_id in config.SCOTTISH_LEAGUE_IDS:
        league = _get(f"/leagues/{league_id}", {"include": "currentSeason"})
        season = (league.get("data") or {}).get("currentSeason")
        if not season:
            continue
        teams = _get(f"/teams/seasons/{season['id']}")
        for team in teams.get("data", []):
            team_ids.add(team["id"])
    return team_ids


def filter_scottish(transfers: list[dict], scottish_team_ids: set[int]) -> list[dict]:
    """
    Keep only transfers involving a team currently in one of the
    configured Scottish leagues.
    """
    if not scottish_team_ids:
        return transfers

    relevant = []
    for t in transfers:
        from_id = (t.get("fromTeam") or {}).get("id")
        to_id = (t.get("toTeam") or {}).get("id")
        if from_id in scottish_team_ids or to_id in scottish_team_ids:
            relevant.append(t)
    return relevant
