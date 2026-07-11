"""
Entry point. Run hourly by GitHub Actions:

  1. Fetch transfers from SportMonks over the trailing TRANSFER_WINDOW_DAYS.
  2. Filter to Scottish leagues, then to ids newer than the last one posted.
  3. For each (oldest first, capped at MAX_TRANSFERS_PER_RUN):
       - build a short vertical video
       - upload it to YouTube as a Short
  4. Update state.json with the newest transfer id we've now posted.
"""
import datetime
import os
import sys
import config
import state
import sportmonks_client
import video_gen
import youtube_upload

TRANSFER_WINDOW_DAYS = 7


def format_fee(transfer: dict) -> str:
    amount = transfer.get("amount")
    if not amount:
        return "Fee undisclosed"
    # SportMonks amounts are typically in the base currency unit (varies by
    # endpoint/plan) - adjust formatting here once you confirm the currency
    # your plan returns.
    return f"€{amount:,.0f}"


def build_title(player: str, from_club: str, to_club: str) -> str:
    return f"{player}: {from_club} ➡ {to_club} | Scottish Football #Shorts"


def build_description(player: str, from_club: str, to_club: str, fee_text: str) -> str:
    return (
        f"{player} moves from {from_club} to {to_club}. {fee_text}.\n\n"
        f"Automated transfer update powered by SportMonks data.\n"
        f"#ScottishFootball #Transfers #Shorts"
    )


def process_transfer(transfer: dict) -> None:
    player = (transfer.get("player") or {}).get("display_name") or (transfer.get("player") or {}).get("name") or "Unknown Player"
    from_team = transfer.get("fromTeam") or {}
    to_team = transfer.get("toTeam") or {}
    from_club = from_team.get("name", "Unknown Club")
    to_club = to_team.get("name", "Unknown Club")
    from_logo = from_team.get("image_path")
    to_logo = to_team.get("image_path")
    fee_text = format_fee(transfer)

    out_path = os.path.join(config.OUTPUT_DIR, f"transfer_{transfer['id']}.mp4")
    print(f"Building video for transfer {transfer['id']}: {player} {from_club} -> {to_club}")
    video_gen.build_video(player, from_club, to_club, fee_text, from_logo, to_logo, out_path)

    title = build_title(player, from_club, to_club)
    description = build_description(player, from_club, to_club, fee_text)

    if config.DRY_RUN:
        print(f"[DRY RUN] Would upload: {title}\n{description}\nFile: {out_path}")
    else:
        video_id = youtube_upload.upload_short(
            out_path, title, description,
            tags=["football", "soccer", "transfers", "scottish football", "shorts"],
        )
        print(f"Uploaded: https://youtube.com/shorts/{video_id}")
        os.remove(out_path)


def main() -> int:
    last_seen = state.load_last_seen_id()
    print(f"Last seen transfer id: {last_seen}")

    end_date = datetime.date.today()
    start_date = end_date - datetime.timedelta(days=TRANSFER_WINDOW_DAYS)
    transfers = sportmonks_client.get_transfers_between(start_date.isoformat(), end_date.isoformat())
    transfers = sportmonks_client.filter_scottish(transfers)

    if last_seen is not None:
        transfers = [t for t in transfers if t["id"] > last_seen]

    if not transfers:
        print("No new transfers.")
        return 0

    # Process oldest -> newest so posting order matches transfer order.
    transfers.sort(key=lambda t: t["id"])
    transfers = transfers[: config.MAX_TRANSFERS_PER_RUN]

    max_id = last_seen or 0
    for transfer in transfers:
        try:
            process_transfer(transfer)
        except Exception as exc:  # noqa: BLE001
            print(f"Failed to process transfer {transfer.get('id')}: {exc}", file=sys.stderr)
            continue
        max_id = max(max_id, transfer["id"])

    state.save_last_seen_id(max_id)
    print(f"Updated state to last_seen_id={max_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
