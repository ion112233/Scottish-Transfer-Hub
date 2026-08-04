"""
Entry point. Run every 8 hours by GitHub Actions:

  1. Scrape Transfermarkt's Scottish Premiership season transfer page
     (retried a few times on transient failure).
  2. Keep only transfers not already seen in a previous scrape (see
     state.py - this is what keeps the pool to roughly "the last 8 hours"
     instead of resurfacing week-old backlog) and drop anything that's
     just a loan expiring (not real transfer news).
  3. Score what's left (fee + market value + club prominence) and take the
     2 most interesting, not just the 2 most recently confirmed.
  4. For each (most interesting first, retried a few times on failure):
       - build a short vertical video
       - upload it to YouTube as a Short
  5. Mark every transfer scraped this run as seen - whether it got posted,
     failed, or simply lost out to a higher-scored one - so nothing gets a
     second window of eligibility once its "last 8 hours" has passed.

Any step that still fails after retries triggers an email alert (see
notify.py) rather than failing silently - the goal is to catch problems
(a broken scrape, a dead YouTube token, a quota outage) as they happen,
since nothing else is watching this run unattended.
"""
import os
import sys

import config
import notify
import ranking
import retry
import scraper
import state
import video_gen
import youtube_upload


def format_fee(transfer: dict) -> str:
    if transfer["fee_type"] == "free":
        return "Free transfer"
    if transfer["fee_type"] in ("loan", "loan_fee"):
        return transfer["fee_text"]
    if transfer["fee_type"] == "fee" and transfer["fee_eur"]:
        return f"€{transfer['fee_eur']:,.0f}"
    return "Fee undisclosed"


def build_title(player: str, from_club: str, to_club: str) -> str:
    return f"{player}: {from_club} ➡ {to_club} | Scottish Football #Shorts"


def club_hashtags(transfer: dict) -> list[str]:
    tags = [config.CLUB_HASHTAGS[cid] for cid in (transfer["from_club_id"], transfer["to_club_id"])
            if cid in config.CLUB_HASHTAGS]
    return list(dict.fromkeys(tags))  # dedupe (same-club loan-style entries), keep order


def build_description(transfer: dict, player: str, from_club: str, to_club: str, fee_text: str,
                       photo_credit: dict | None, music_credit: str) -> str:
    description = (
        f"{player} moves from {from_club} to {to_club}. {fee_text}.\n\n"
        f"Automated transfer update, sourced from Transfermarkt.\n"
    )
    if photo_credit:
        description += (
            f"Player photo: {photo_credit['artist']}, {photo_credit['license']}, "
            f"via Wikimedia Commons ({photo_credit['url']}).\n"
        )
    description += f"{music_credit}\n"
    hashtags = ["#ScottishFootball", "#Transfers", "#Shorts", *club_hashtags(transfer)]
    description += " ".join(hashtags)
    return description


def process_transfer(transfer: dict) -> None:
    player = transfer["player_name"]
    from_club, to_club = transfer["from_club"], transfer["to_club"]
    fee_text = format_fee(transfer)

    out_path = os.path.join(config.OUTPUT_DIR, f"transfer_{transfer['transfer_id']}.mp4")
    print(f"Building video for transfer {transfer['transfer_id']} (score {transfer['score']:.3f}): "
          f"{player} {from_club} -> {to_club}")
    _, photo_credit, music_credit = video_gen.build_video(
        player, from_club, to_club, fee_text,
        transfer["from_club_logo"], transfer["to_club_logo"], out_path,
        transfer_id=transfer["transfer_id"],
    )
    if photo_credit:
        print(f"Using player photo: {photo_credit['title']} ({photo_credit['license']}, {photo_credit['artist']})")
    else:
        print("No suitable free player photo found - using default background.")

    title = build_title(player, from_club, to_club)
    description = build_description(transfer, player, from_club, to_club, fee_text, photo_credit, music_credit)
    tags = ["football", "soccer", "transfers", "scottish football", "shorts", from_club.lower(), to_club.lower()]

    if config.DRY_RUN:
        print(f"[DRY RUN] Would upload: {title}\n{description}\nFile: {out_path}")
    else:
        video_id = youtube_upload.upload_short(out_path, title, description, tags=tags)
        print(f"Uploaded: https://youtube.com/shorts/{video_id}")
        # Cleanup failing here must not look like the upload itself failed -
        # that would make the retry wrapper around this function re-run it
        # and double-post, since the upload already succeeded.
        try:
            os.remove(out_path)
        except OSError as exc:
            print(f"Warning: couldn't remove {out_path}: {exc}", file=sys.stderr)


def _run() -> int:
    seen_ids = state.load_seen_ids()
    print(f"{len(seen_ids)} transfers already seen in a previous run.")

    season_id = config.SEASON_ID_OVERRIDE or scraper.current_season_id()
    try:
        transfers = retry.retry(
            lambda: scraper.get_scottish_premiership_transfers(season_id),
            config.RETRY_ATTEMPTS, config.RETRY_BASE_DELAY, "Scraping Transfermarkt",
        )
    except Exception as exc:  # noqa: BLE001
        notify.send(
            "Scrape failed - no transfers checked this run",
            f"Scraping Transfermarkt (season {season_id}) failed after "
            f"{config.RETRY_ATTEMPTS} attempts:\n\n{exc}",
        )
        return 1
    print(f"Scraped {len(transfers)} transfers for season {season_id}.")

    new_transfers = [t for t in transfers if t["transfer_id"] not in seen_ids]
    print(f"{len(new_transfers)} of those are new since the last check (~last 8h).")

    ranked = ranking.rank(new_transfers)
    to_post = ranked[: config.MAX_TRANSFERS_PER_RUN]

    all_scraped_ids = {t["transfer_id"] for t in transfers}
    if config.DRY_RUN:
        print(f"[DRY RUN] Not updating state (would mark {len(all_scraped_ids - seen_ids)} ids as seen).")
    else:
        state.save_seen_ids(seen_ids | all_scraped_ids)
        print(f"Marked {len(all_scraped_ids)} scraped transfers as seen.")

    if not to_post:
        print("No new transfers to post.")
        return 0

    newly_posted = set()
    failures = []
    for transfer in to_post:
        try:
            retry.retry(
                lambda t=transfer: process_transfer(t),
                config.RETRY_ATTEMPTS, config.RETRY_BASE_DELAY,
                f"Processing transfer {transfer['transfer_id']} ({transfer['player_name']})",
            )
        except Exception as exc:  # noqa: BLE001
            print(f"Giving up on transfer {transfer.get('transfer_id')}: {exc}", file=sys.stderr)
            failures.append((transfer, exc))
            continue
        newly_posted.add(transfer["transfer_id"])

    if failures:
        body = "\n".join(
            f"- {t['player_name']} ({t['from_club']} -> {t['to_club']}, id {t['transfer_id']}): {exc}"
            for t, exc in failures
        )
        notify.send(
            f"{len(failures)} transfer(s) failed after {config.RETRY_ATTEMPTS} attempts",
            f"These are already marked seen and won't be retried next run - "
            f"only genuinely new transfers get picked up going forward:\n\n{body}",
        )
    print(f"Posted {len(newly_posted)}/{len(to_post)} transfers this run.")

    if to_post and not newly_posted:
        # Every attempted transfer failed - fail the Action run itself (not
        # just the email alert) so GitHub's own failure notification is a
        # second line of defense if email alerts aren't configured.
        return 1
    return 0


def main() -> int:
    try:
        return _run()
    except Exception as exc:  # noqa: BLE001
        notify.send("Run crashed", f"Unhandled error:\n\n{exc}")
        raise


if __name__ == "__main__":
    raise SystemExit(main())
