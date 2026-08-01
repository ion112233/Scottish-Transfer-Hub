"""
Scrapes confirmed transfers involving Scottish Premiership clubs from
Transfermarkt's public season transfer page (one request per run):

  https://www.transfermarkt.com/scottish-premiership/transfers/wettbewerb/SC1/saison_id/{season_id}

That page lists, for every Premiership club, an "In" (Arrivals) table and an
"Out" (Departures) table. Scanning both and deduping by transfer_id covers
transfers in either direction, including moves to/from clubs outside the
league (e.g. a player leaving Celtic for a club abroad).
"""
import datetime
import re

import requests
from bs4 import BeautifulSoup

import config

BASE_URL = "https://www.transfermarkt.com/scottish-premiership/transfers/wettbewerb/SC1"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}

FEE_MULTIPLIERS = {"k": 1_000, "m": 1_000_000}


def current_season_id(today: datetime.date | None = None) -> int:
    """
    Transfermarkt season ids are the year a season starts. Scottish football
    seasons run roughly August-May, with the summer transfer window (the one
    that matters most for "new" transfers) closing in early September, so
    treat July onward as belonging to the season starting that year.
    """
    today = today or datetime.date.today()
    return today.year if today.month >= 7 else today.year - 1


def _parse_money(text: str) -> int | None:
    text = text.strip()
    m = re.match(r"€([\d.]+)([km])", text)
    if not m:
        return None
    return round(float(m.group(1)) * FEE_MULTIPLIERS[m.group(2)])


def _parse_fee_cell(cell) -> dict:
    """
    Returns {"fee_type": ..., "fee_eur": int|None, "fee_text": str}.
    fee_type is one of: fee, free, loan, loan_fee, end_of_loan, unknown.
    """
    link = cell.find("a")
    if link is None:
        return {"fee_type": "unknown", "fee_eur": None, "fee_text": cell.get_text(strip=True)}

    # "End of loan" and "Loan fee: ..." cells wrap the label and a date/amount
    # in an <i> tag inside the same <a> - pull the label out separately.
    italic = link.find("i")
    label = link.get_text(" ", strip=True)
    if italic is not None:
        label = link.get_text(strip=True, separator="\x00").split("\x00")[0]

    if label.lower().startswith("end of loan"):
        return {"fee_type": "end_of_loan", "fee_eur": None, "fee_text": label}
    if label.lower() == "free transfer":
        return {"fee_type": "free", "fee_eur": 0, "fee_text": label}
    if label.lower().startswith("loan fee"):
        amount_text = italic.get_text(strip=True) if italic else ""
        return {"fee_type": "loan_fee", "fee_eur": _parse_money(amount_text), "fee_text": f"Loan (fee: {amount_text})"}
    if label.lower() == "loan transfer":
        return {"fee_type": "loan", "fee_eur": None, "fee_text": label}
    if label in ("-", "?"):
        return {"fee_type": "unknown", "fee_eur": None, "fee_text": "Undisclosed"}

    amount = _parse_money(label)
    if amount is not None:
        return {"fee_type": "fee", "fee_eur": amount, "fee_text": label}
    return {"fee_type": "unknown", "fee_eur": None, "fee_text": label}


def _transfer_id_from_fee_cell(cell) -> int | None:
    link = cell.find("a")
    if link is None or not link.get("href"):
        return None
    m = re.search(r"/transfer_id/(\d+)", link["href"])
    return int(m.group(1)) if m else None


def _parse_market_value(text: str) -> int | None:
    return _parse_money(text.strip())


def _club_id_from_href(href: str) -> int | None:
    m = re.search(r"/verein/(\d+)", href)
    return int(m.group(1)) if m else None


def _crest_url(link) -> str | None:
    """Extracts a club crest <img> src from a link and upsizes it to the
    'big' (180x180) variant - the tables otherwise link 'tiny' (30x30)."""
    img = link.find("img") if link else None
    if img is None or not img.get("src"):
        return None
    return re.sub(r"/wappen/[a-zA-Z]+/", "/wappen/big/", img["src"])


def _parse_table_rows(table, direction: str) -> list[dict]:
    rows = []
    body = table.find("tbody")
    if body is None:
        return rows
    for tr in body.find_all("tr"):
        cells = tr.find_all("td")
        if len(cells) < 9:
            continue
        player_link = cells[0].find("a")
        if player_link is None:
            continue
        player_id_match = re.search(r"/spieler/(\d+)", player_link.get("href", ""))
        counterpart_link = cells[6].find("a")
        if counterpart_link is None:
            continue
        fee_info = _parse_fee_cell(cells[8])
        transfer_id = _transfer_id_from_fee_cell(cells[8])
        if transfer_id is None:
            continue

        rows.append({
            "transfer_id": transfer_id,
            "direction": direction,
            "player_name": player_link.get_text(strip=True),
            "player_id": int(player_id_match.group(1)) if player_id_match else None,
            "age": cells[1].get_text(strip=True) or None,
            "position": cells[3].get_text(strip=True) or None,
            "market_value_eur": _parse_market_value(cells[5].get_text()),
            # The crest-only <a> in this cell wraps just an <img> (no text
            # content) - its title attribute has the full club name.
            "counterpart_club": counterpart_link.get("title") or counterpart_link.get_text(strip=True),
            "counterpart_club_id": _club_id_from_href(counterpart_link.get("href", "")),
            "counterpart_club_logo": _crest_url(counterpart_link),
            **fee_info,
        })
    return rows


def _parse_club_boxes(soup: BeautifulSoup) -> list[dict]:
    transfers_by_id: dict[int, dict] = {}

    for heading in soup.select('h2[id^="to-"]'):
        club_id_match = re.match(r"to-(\d+)", heading.get("id", ""))
        if not club_id_match:
            continue
        club_id = int(club_id_match.group(1))
        club_link = heading.find("a", title=True)
        # The first <a> wraps only the crest <img> (empty text content) - the
        # clean name is in its title attribute; get_text() would need the
        # second <a>, whose title has a stray "Array" suffix on this page.
        club_name = club_link.get("title") if club_link else None
        club_logo = _crest_url(club_link)

        box = heading.find_parent("div", class_="box")
        if box is None:
            continue
        tables = box.select("div.responsive-table > table")
        if len(tables) < 2:
            continue

        arrivals = _parse_table_rows(tables[0], "in")
        departures = _parse_table_rows(tables[1], "out")

        for row in arrivals + departures:
            if row["fee_type"] == "end_of_loan":
                continue
            tid = row["transfer_id"]
            if tid in transfers_by_id:
                continue  # already captured from the other side of this move

            if row["direction"] == "in":
                from_club, from_club_id, from_logo = row["counterpart_club"], row["counterpart_club_id"], row["counterpart_club_logo"]
                to_club, to_club_id, to_logo = club_name, club_id, club_logo
            else:
                from_club, from_club_id, from_logo = club_name, club_id, club_logo
                to_club, to_club_id, to_logo = row["counterpart_club"], row["counterpart_club_id"], row["counterpart_club_logo"]

            transfers_by_id[tid] = {
                "transfer_id": tid,
                "player_name": row["player_name"],
                "player_id": row["player_id"],
                "age": row["age"],
                "position": row["position"],
                "market_value_eur": row["market_value_eur"],
                "from_club": from_club,
                "from_club_id": from_club_id,
                "from_club_logo": from_logo,
                "to_club": to_club,
                "to_club_id": to_club_id,
                "to_club_logo": to_logo,
                "fee_type": row["fee_type"],
                "fee_eur": row["fee_eur"],
                "fee_text": row["fee_text"],
            }

    return list(transfers_by_id.values())


def fetch_page(season_id: int) -> str:
    url = f"{BASE_URL}/saison_id/{season_id}"
    resp = requests.get(url, headers=HEADERS, timeout=config.REQUEST_TIMEOUT)
    resp.raise_for_status()
    return resp.text


def get_scottish_premiership_transfers(season_id: int | None = None) -> list[dict]:
    season_id = season_id or current_season_id()
    html = fetch_page(season_id)
    soup = BeautifulSoup(html, "lxml")
    return _parse_club_boxes(soup)
