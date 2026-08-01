# Transfer Web Scrapper

Every 8 hours, this scrapes Transfermarkt for confirmed Scottish Premiership
transfers, scores them for how "interesting" they are (fee + player market
value + club prominence), and posts an auto-generated YouTube Short for the
2 most interesting ones it hasn't posted yet - up to 6 Shorts/day across the
3 daily runs, matched to YouTube's default API upload quota, fewer whenever
there aren't 2 interesting unposted transfers in the pool. Runs entirely on
GitHub Actions' free tier — no server needed.

This replaces the SportMonks-API-based bot that used to live in this same
repo (posting hourly to the same YouTube channel) - its source has been
moved to `ARHIVED/` (untracked, local-only, see `.gitignore`) rather than
running both and double-posting.

## How it works

1. `main.py` runs every 8 hours (`.github/workflows/eight-hourly-transfers.yml`).
2. `scraper.py` scrapes Transfermarkt's Scottish Premiership season transfers
   page (one request per run) and parses every confirmed transfer, in either
   direction, involving a Premiership club — arrivals and departures alike.
   "End of loan" entries (a player just returning from a loan spell) are
   filtered out as not real transfer news.
3. Anything already in `state.json` is dropped, then `ranking.py` scores
   what's left: 45% transfer fee, 30% the player's Transfermarkt market
   value, 25% club prominence (Celtic/Rangers weighted highest, other
   Premiership clubs next, anyone else — a foreign or lower-league
   counterpart club — a flat baseline).
4. The top 2 scores overall (not just the 2 most recent) get a video each:
   `video_gen.py` renders a 1080×1920 vertical clip (player name, club
   crests, fee, TTS voiceover) with Pillow + MoviePy + edge-tts. The
   background is a real photo of the player in match/training action when
   one can be found - see "Player photos" below - falling back to a flat
   gradient otherwise.
5. `youtube_upload.py` uploads each as a public YouTube Short, with a
   description that includes club-specific hashtags (e.g. `#Celtic`,
   `#Rangers`) for whichever clubs are in that transfer, on top of the
   static `#ScottishFootball #Transfers #Shorts`.
6. `state.json` is updated so the same transfer is never posted twice.

Any step that fails is retried a few times before being treated as a real
failure - see "Reliability" below.

## Player photos

`player_image.py` looks up a background photo on **Wikimedia Commons only**
- not a general image search - because Commons exclusively hosts
freely-licensed media (CC0/CC-BY/CC-BY-SA), whereas most football action
photos elsewhere belong to press agencies (Getty, PA Images, etc.) and can't
legally be used on a public YouTube channel.

Two checks run before a photo is trusted, because Commons' full-text search
alone isn't a reliable identity match (e.g. searching a player's name can
surface an unrelated namesake):

1. **Identity**: the photo must carry a Commons category matching the
   player's own name - the convention Commons uses to file every photo of a
   specific person - not just a search-relevance match.
2. **Context**: the photo must show positive evidence of being actual match
   or training action (a fixture-style category like "Team A v Team B", a
   scoreline, or an explicit "open practice"/"training" category), and must
   not carry any ceremonial/political terms (award shows, government
   meetings, etc.) even if the player does appear in one.

If no photo passes both checks - common for lower-profile squad players
with little or no Commons coverage - `video_gen.py` falls back to the
default gradient background. When a photo *is* used, its artist and license
are automatically credited in the video's description, as CC-BY/CC-BY-SA
require.

## Background music

Every video has a light instrumental bed (12% volume, well under the
voiceover) from `assets/background_music.mp3` - **"New Hero in Town" by
Kevin MacLeod (incompetech.com)**, licensed under
[Creative Commons: By Attribution 4.0](https://creativecommons.org/licenses/by/4.0/),
which explicitly permits free use in videos with attribution, no
registration required. That credit is included in every video's
description automatically (`config.MUSIC_CREDIT`) - if you swap the track,
update that constant to match the new license.

## Reliability

This runs completely unattended, so failures need to be visible without
anyone watching the logs:

- **Retries**: scraping and each transfer's build-and-upload are retried up
  to `RETRY_ATTEMPTS` times (default 3, exponential backoff from
  `RETRY_BASE_DELAY` seconds) via `retry.py` before being treated as a real
  failure. A transfer that still fails after retries just stays unposted
  and gets picked up again next run - nothing is lost.
- **Email alerts** (`notify.py`): if the scrape fails entirely, a transfer
  fails after all retries, or the run hits an unhandled error, an email is
  sent via Gmail SMTP. This is optional - if `GMAIL_ADDRESS` /
  `GMAIL_APP_PASSWORD` aren't set, it just logs instead of sending. See
  "Email alerts" under setup for how to configure it.
- **Self-healing by design**: because each run re-scrapes the *entire*
  season and re-ranks the whole unposted pool (not just "what's new since
  last time"), a missed or failed run never loses a transfer - it's simply
  reconsidered, and re-ranked against everything else, next time.

## One-time setup

### 1. YouTube (Google Cloud + OAuth)

This repo already has `YOUTUBE_CLIENT_ID` / `YOUTUBE_CLIENT_SECRET` /
`YOUTUBE_REFRESH_TOKEN` configured as GitHub secrets from the previous
project that lived here, targeting the same YouTube channel - nothing to
redo, skip straight to step 2.

Only needed if you ever have to regenerate those (e.g. the refresh token
gets revoked):

1. In [Google Cloud Console](https://console.cloud.google.com/), create a
   project and enable **YouTube Data API v3**.
2. Configure the OAuth consent screen (External is fine; you can leave it
   in "Testing" mode as long as you add your own Google account as a test
   user — this avoids Google's verification review).
3. Create OAuth 2.0 credentials → Application type **Desktop app**. Download
   the `client_secret.json`.
4. Locally (not in CI), run:
   ```
   pip install google-auth-oauthlib
   python get_youtube_token.py
   ```
   This opens a browser, asks you to log into the YouTube channel you want
   to post to, and prints a `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`,
   and `YOUTUBE_REFRESH_TOKEN`. Save these — you'll paste them into GitHub
   secrets next.

### 2. Email alerts (optional, but recommended)

1. Turn on 2-Step Verification on the Google account you want alerts sent
   from, if it isn't already (required for the next step).
2. Generate an App Password at
   [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
   (name it something like "Transfer Web Scrapper") - it's a 16-character
   password scoped to just this use, separate from your real Google
   password.
3. Save that address and app password — you'll paste them into GitHub
   secrets next, along with where alerts should be sent (can be the same
   address, or a different inbox).

Skip this and the run still works exactly the same - failures just get
logged instead of emailed.

### 3. GitHub repo secrets

Under **Settings → Secrets and variables → Actions** on this repo:

| Secret | Value |
|---|---|
| `YOUTUBE_CLIENT_ID` | already set (carried over from the previous project) |
| `YOUTUBE_CLIENT_SECRET` | already set |
| `YOUTUBE_REFRESH_TOKEN` | already set |
| `GMAIL_ADDRESS` | the Gmail address from step 2 (optional, new) |
| `GMAIL_APP_PASSWORD` | the app password from step 2 (optional, new) |
| `NOTIFY_EMAIL` | where alerts should land (optional, new - defaults to `GMAIL_ADDRESS` if unset) |

No scraping-side secret is needed — Transfermarkt's transfer pages are
public.

### 4. Test it

Go to the **Actions** tab → "Eight-hourly transfer check" → **Run workflow**
→ tick **dry_run** → Run. This builds the video(s) but skips the YouTube
upload, so you can check the logs and download the rendered clips as a
workflow artifact first. Once you're happy, run it again with dry_run
unticked, or just let the 8-hourly cron take over.

## Customizing

- **Video look:** edit `video_gen.py` (`build_frame`) — the background is a
  purple/gold "thistle" theme, deliberately neutral between Celtic and
  Rangers; colors and fonts (Liberation Sans) live at the top of the file.
- **Voiceover:** `TTS_VOICE` env var (default `en-GB-RyanNeural`) picks the
  edge-tts voice — see `edge-tts --list-voices` for alternatives.
- **Ranking weights:** `FEE_WEIGHT` / `MARKET_VALUE_WEIGHT` / `CLUB_WEIGHT`
  and the fee/market-value caps in `config.py`.
- **Posting cap:** `MAX_TRANSFERS_PER_RUN` in `config.py` (default 2).
- **Cron schedule:** edit the `cron:` line in the workflow file. GitHub
  Actions cron times are UTC and can be delayed a few minutes during high
  load — fine for an 8-hourly check like this.
- **Club hashtags:** `CLUB_HASHTAGS` in `config.py` — add/edit per club.
- **Background music:** swap `assets/background_music.mp3` for another
  freely-licensed track and update `MUSIC_CREDIT`/`MUSIC_VOLUME` in
  `config.py` to match.
- **Retries:** `RETRY_ATTEMPTS` / `RETRY_BASE_DELAY` in `config.py`.

## Scraping etiquette

Only one HTTP request is made per run (the season transfers page covers all
12 Premiership clubs at once), with a browser-like User-Agent and a 30s
timeout. Transfermarkt's terms restrict automated scraping, so keep the
request volume low if you extend this further, and consider reaching out to
them for permission if you plan to scale this up.

## Costs

- GitHub Actions: free for public repos; ~2,000 free minutes/month for
  private repos, and this job takes a couple of minutes per run.
- Transfermarkt: free, no API key.
- YouTube Data API: free, but has a daily quota (10,000 units/day by
  default); each upload costs ~1,600 units, so you're capped around
  6 uploads/day unless you request a quota increase - 2 per run × 3 runs/day
  stays right at that cap.
