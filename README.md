# Scottish Football Transfer Shorts Bot

Every hour, this checks SportMonks for new Scottish football transfers and
posts an auto-generated YouTube Short for each new one. Runs entirely on
GitHub Actions' free tier — no server needed.

## How it works

1. `main.py` runs on a cron schedule (`.github/workflows/hourly-transfers.yml`).
2. It asks SportMonks for transfers newer than the last one it has already
   posted (tracked in `state.json`, committed back to the repo each run).
3. For each new transfer, `video_gen.py` renders a 1080×1920 vertical video
   (player name, club crests, fee, TTS voiceover) with Pillow + MoviePy + gTTS.
4. `youtube_upload.py` uploads it as a public YouTube Short.
5. `state.json` is updated so the same transfer never gets posted twice.

## One-time setup

### 1. SportMonks

1. Sign up at sportmonks.com and grab your API token from your dashboard.
2. Confirm the Scottish league IDs your plan includes. Call:
   `https://api.sportmonks.com/v3/football/leagues?api_token=YOUR_TOKEN&search=scottish`
   and note the `id` fields — set these as `SCOTTISH_LEAGUE_IDS` (see secrets
   below). The defaults in `config.py` are placeholders and **should be
   verified against your actual subscription** before relying on them.

> Note: I wasn't able to make live calls to the SportMonks API while
> building this (no network access in this environment), so the request
> shapes here follow their published docs but haven't been tested against
> a real API key. Run once with `DRY_RUN=true` (see below) and check the
> Action logs before trusting it to post publicly.

### 2. YouTube (Google Cloud + OAuth)

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

### 3. GitHub repo secrets

Push this project to a new GitHub repo, then under
**Settings → Secrets and variables → Actions**, add:

| Secret | Value |
|---|---|
| `SPORTMONKS_API_TOKEN` | your SportMonks token |
| `SCOTTISH_LEAGUE_IDS` | comma-separated league IDs, e.g. `501,502,503,504` |
| `YOUTUBE_CLIENT_ID` | from step 2 |
| `YOUTUBE_CLIENT_SECRET` | from step 2 |
| `YOUTUBE_REFRESH_TOKEN` | from step 2 |

### 4. Test it

Go to the **Actions** tab → "Hourly transfer check" → **Run workflow** →
tick **dry_run** → Run. This builds the video(s) but skips the YouTube
upload, so you can check the logs are healthy first. Once you're happy,
run it again with dry_run unticked, or just let the hourly cron take over.

## Customizing

- **Video look:** edit `video_gen.py` (`build_frame`) — colors, layout, fonts.
- **Voiceover:** swap `gTTS` for another TTS engine in `video_gen.py` if you
  want a different voice.
- **Posting cap:** `MAX_TRANSFERS_PER_RUN` in `config.py` limits how many
  transfers get posted per hourly run (default 3), in case of a busy
  transfer-window burst.
- **Cron schedule:** edit the `cron:` line in the workflow file. GitHub Actions
  cron times are UTC and can be delayed a few minutes during high load —
  fine for an hourly check like this.

## Costs

- GitHub Actions: free for public repos; ~2,000 free minutes/month for
  private repos, and this job takes well under a minute per run with no new
  transfers, more like 1–3 minutes on runs that render videos.
- SportMonks: free plan (Scottish leagues).
- YouTube Data API: free, but has a daily quota (10,000 units/day by
  default); each upload costs ~1,600 units, so you're capped around
  6 uploads/day unless you request a quota increase.
