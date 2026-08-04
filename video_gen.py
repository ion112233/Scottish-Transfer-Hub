"""
Builds a short vertical (1080x1920) MP4 announcing a single transfer, as
three quick shots rather than one static card sitting still the whole time:

  1. Intro - player name reveal
  2. Main  - club crests + "FROM -> TO"
  3. Outro - fee reveal + follow CTA + brand watermark

with word-synced animated captions over the whole thing (from edge-tts's
word-boundary timestamps) and a light music bed, picked per-video from a
small rotation so the same track isn't heard on every single upload.
"""
import asyncio
import io
import os
import re

import edge_tts
import requests
from PIL import Image, ImageDraw, ImageFont

# moviepy 1.0.3's resize effect still calls Image.ANTIALIAS, which Pillow
# removed in v10. Restore it as an alias before moviepy needs it.
if not hasattr(Image, "ANTIALIAS"):
    Image.ANTIALIAS = Image.LANCZOS

from moviepy.editor import (
    ImageClip, AudioFileClip, CompositeVideoClip, CompositeAudioClip,
    concatenate_videoclips, vfx,
)
from moviepy.audio.fx.all import audio_loop, volumex

import config
import player_image

W, H = 1080, 1920

# Installed via apt in the workflow (fonts-liberation).
FONT_BOLD = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
FONT_REGULAR = "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"

# Thistle-purple gradient (nods to Scotland's national flower rather than
# either Old Firm club's colours) with a gold accent.
BG_TOP = (24, 10, 38)
BG_BOTTOM = (72, 24, 92)
ACCENT = (245, 185, 66)
WHITE = (255, 255, 255)

# Both the Transfermarkt crest CDN and Wikimedia's image CDN 403 requests
# that don't carry a browser-like User-Agent.
DOWNLOAD_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}

SHOT_TRANSITION = 0.2      # crossfade seconds between shots
CAPTION_WORDS_PER_CHUNK = 3
CAPTION_Y_FRACTION = 0.70  # lower-third, clear of crests/name/fee layout
TTS_RATE_VARIANTS = ["-4%", "+0%", "+4%"]  # slight per-video pacing variety


# --- Backgrounds -----------------------------------------------------------

def _gradient_bg() -> Image.Image:
    img = Image.new("RGB", (W, H), BG_TOP)
    draw = ImageDraw.Draw(img)
    for y in range(H):
        t = y / H
        r = int(BG_TOP[0] + (BG_BOTTOM[0] - BG_TOP[0]) * t)
        g = int(BG_TOP[1] + (BG_BOTTOM[1] - BG_TOP[1]) * t)
        b = int(BG_TOP[2] + (BG_BOTTOM[2] - BG_TOP[2]) * t)
        draw.line([(0, y), (W, y)], fill=(r, g, b))
    return img


def _download_logo(url: str | None, size: int = 260) -> Image.Image | None:
    if not url:
        return None
    try:
        resp = requests.get(url, headers=DOWNLOAD_HEADERS, timeout=15)
        resp.raise_for_status()
        logo = Image.open(io.BytesIO(resp.content)).convert("RGBA")
        logo.thumbnail((size, size))
        return logo
    except Exception:
        return None


def _download_photo(url: str) -> Image.Image | None:
    try:
        resp = requests.get(url, headers=DOWNLOAD_HEADERS, timeout=20)
        resp.raise_for_status()
        return Image.open(io.BytesIO(resp.content)).convert("RGB")
    except Exception:
        return None


def _cover_crop(img: Image.Image, target_w: int, target_h: int) -> Image.Image:
    """Resizes+center-crops img to exactly fill target_w x target_h, like CSS
    'background-size: cover'."""
    src_ratio = img.width / img.height
    target_ratio = target_w / target_h
    if src_ratio > target_ratio:
        new_h = target_h
        new_w = round(new_h * src_ratio)
    else:
        new_w = target_w
        new_h = round(new_w / src_ratio)
    img = img.resize((new_w, new_h), Image.LANCZOS)
    left = (new_w - target_w) // 2
    top = (new_h - target_h) // 2
    return img.crop((left, top, left + target_w, top + target_h))


def _photo_bg(photo: Image.Image) -> Image.Image:
    """Cover-crops the player photo to the frame and darkens it - heavily at
    the top and bottom, lightly through the middle - so overlaid text and
    crests stay legible over a busy action shot."""
    bg = _cover_crop(photo, W, H).convert("RGBA")
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)
    top_band, bottom_start = H * 0.4, H * 0.55
    plateau_alpha, top_alpha, bottom_alpha = 60, 215, 250
    for y in range(H):
        # Piecewise-linear fade that shares the plateau value at both
        # breakpoints, so there's no visible seam where the pieces meet.
        if y < top_band:
            alpha = top_alpha - (top_alpha - plateau_alpha) * (y / top_band)
        elif y > bottom_start:
            alpha = plateau_alpha + (bottom_alpha - plateau_alpha) * ((y - bottom_start) / (H - bottom_start))
        else:
            alpha = plateau_alpha
        odraw.line([(0, y), (W, y)], fill=(8, 4, 14, int(alpha)))
    return Image.alpha_composite(bg, overlay).convert("RGB")


def _base_bg(player_photo: Image.Image | None) -> Image.Image:
    return _photo_bg(player_photo) if player_photo is not None else _gradient_bg()


def _wrapped_text(draw, text, font, max_width):
    lines, line = [], ""
    for word in text.split():
        test = f"{line} {word}".strip()
        if draw.textlength(test, font=font) <= max_width:
            line = test
        else:
            lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


def _watermark_badge(size: int = 120) -> Image.Image:
    badge = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(badge)
    draw.ellipse((2, 2, size - 2, size - 2), fill=(24, 10, 38, 215),
                 outline=ACCENT + (255,), width=max(3, size // 30))
    font = ImageFont.truetype(FONT_BOLD, int(size * 0.30))
    text = config.WATERMARK_TEXT
    tw = draw.textlength(text, font=font)
    draw.text(((size - tw) / 2, size / 2 - size * 0.19), text, font=font, fill=ACCENT)
    return badge


# --- Shots -------------------------------------------------------------

def build_intro_frame(player_name: str, player_photo: Image.Image | None) -> Image.Image:
    img = _base_bg(player_photo).convert("RGBA")
    draw = ImageDraw.Draw(img)

    font_title = ImageFont.truetype(FONT_BOLD, 58)
    font_player = ImageFont.truetype(FONT_BOLD, 96)

    header = "TRANSFER CONFIRMED"
    tw = draw.textlength(header, font=font_title)
    draw.text(((W - tw) / 2, H * 0.33), header, font=font_title, fill=ACCENT)

    lines = _wrapped_text(draw, player_name.upper(), font_player, W - 140)
    y = H * 0.43
    for line in lines:
        tw = draw.textlength(line, font=font_player)
        draw.text(((W - tw) / 2, y), line, font=font_player, fill=WHITE)
        y += 108

    badge = _watermark_badge()
    img.paste(badge, (40, 40), badge)
    return img.convert("RGB")


def build_main_frame(player_name: str, from_club: str, to_club: str,
                      from_logo_url: str | None, to_logo_url: str | None,
                      player_photo: Image.Image | None) -> Image.Image:
    img = _base_bg(player_photo).convert("RGBA")
    draw = ImageDraw.Draw(img)

    font_player = ImageFont.truetype(FONT_BOLD, 54)
    font_club = ImageFont.truetype(FONT_REGULAR, 46)
    font_arrow = ImageFont.truetype(FONT_BOLD, 90)

    lines = _wrapped_text(draw, player_name.upper(), font_player, W - 160)
    y = 150
    for line in lines:
        tw = draw.textlength(line, font=font_player)
        draw.text(((W - tw) / 2, y), line, font=font_player, fill=WHITE)
        y += 64

    logo_y = int(H * 0.40)
    from_logo = _download_logo(from_logo_url)
    to_logo = _download_logo(to_logo_url)
    left_x, right_x = W // 4, 3 * W // 4

    if from_logo:
        img.paste(from_logo, (left_x - from_logo.width // 2, logo_y), from_logo)
    if to_logo:
        img.paste(to_logo, (right_x - to_logo.width // 2, logo_y), to_logo)

    arrow_y = logo_y + 100
    draw.text((W // 2 - 30, arrow_y), "→", font=font_arrow, fill=ACCENT)

    name_y = logo_y + 280
    for club, cx in ((from_club, left_x), (to_club, right_x)):
        cl = _wrapped_text(draw, club, font_club, W // 2 - 40)
        yy = name_y
        for line in cl:
            tw = draw.textlength(line, font=font_club)
            draw.text((cx - tw / 2, yy), line, font=font_club, fill=WHITE)
            yy += 54

    badge = _watermark_badge()
    img.paste(badge, (40, 40), badge)
    return img.convert("RGB")


def build_outro_frame(fee_text: str, player_photo: Image.Image | None) -> Image.Image:
    img = _base_bg(player_photo).convert("RGBA")
    draw = ImageDraw.Draw(img)

    font_label = ImageFont.truetype(FONT_REGULAR, 42)
    font_fee = ImageFont.truetype(FONT_BOLD, 92)
    font_cta = ImageFont.truetype(FONT_BOLD, 48)
    font_footer = ImageFont.truetype(FONT_REGULAR, 34)

    label = "TRANSFER FEE"
    tw = draw.textlength(label, font=font_label)
    draw.text(((W - tw) / 2, H * 0.36), label, font=font_label, fill=(210, 190, 220))

    if fee_text:
        fee_lines = _wrapped_text(draw, fee_text, font_fee, W - 100)
        yy = H * 0.42
        for line in fee_lines:
            tw = draw.textlength(line, font=font_fee)
            draw.text(((W - tw) / 2, yy), line, font=font_fee, fill=ACCENT)
            yy += 104

    cta = "FOLLOW FOR MORE"
    tw = draw.textlength(cta, font=font_cta)
    draw.text(((W - tw) / 2, H * 0.62), cta, font=font_cta, fill=WHITE)

    badge = _watermark_badge(size=170)
    img.paste(badge, ((W - badge.width) // 2, int(H * 0.70)), badge)

    footer = "Scottish Football Transfers"
    tw = draw.textlength(footer, font=font_footer)
    draw.text(((W - tw) / 2, H - 90), footer, font=font_footer, fill=(210, 190, 220))

    return img.convert("RGB")


# --- Voiceover + word-synced captions ---------------------------------

def _synthesize_speech_with_words(text: str, voice: str, rate: str, out_path: str) -> list[dict]:
    """Saves the narration audio to out_path and returns word timings
    ([{"text", "start", "end"}, ...] in seconds) from edge-tts's
    WordBoundary events."""
    async def _run():
        communicate = edge_tts.Communicate(text, voice, rate=rate, boundary="WordBoundary")
        words = []
        with open(out_path, "wb") as f:
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    f.write(chunk["data"])
                elif chunk["type"] == "WordBoundary":
                    words.append({
                        "text": chunk["text"],
                        "start": chunk["offset"] / 1e7,
                        "end": (chunk["offset"] + chunk["duration"]) / 1e7,
                    })
        return words

    return asyncio.run(_run())


def _sentence_word_counts(text: str) -> list[int]:
    sentences = [s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s]
    return [len(s.split()) for s in sentences]


def _group_captions(words: list[dict], sentence_word_counts: list[int],
                     words_per_chunk: int = CAPTION_WORDS_PER_CHUNK) -> list[dict]:
    """Groups words into short caption chunks, breaking early at sentence
    ends (rather than always taking a fixed count) so a chunk never reads
    as a run-on across two sentences, e.g. "...TOWN TRANSFER..." bleeding
    the end of one sentence into the next. edge-tts's WordBoundary events
    don't retain punctuation in the word text, so sentence ends can't be
    detected from the words themselves - sentence_word_counts (word counts
    per sentence in the original source text) locates them positionally
    instead."""
    boundary_indices = set()
    idx = 0
    for count in sentence_word_counts:
        idx += count
        boundary_indices.add(idx - 1)

    chunks, current = [], []

    def _flush():
        if current:
            chunks.append({
                "text": " ".join(w["text"] for w in current),
                "start": current[0]["start"],
                "end": current[-1]["end"],
            })
            current.clear()

    for i, w in enumerate(words):
        current.append(w)
        if len(current) >= words_per_chunk or i in boundary_indices:
            _flush()
    _flush()
    return chunks


def _render_caption_image(text: str) -> Image.Image:
    font = ImageFont.truetype(FONT_BOLD, 62)
    dummy = ImageDraw.Draw(Image.new("RGBA", (10, 10)))
    upper = text.upper()
    tw = dummy.textlength(upper, font=font)
    pad_x, pad_y, stroke_w = 40, 26, 6
    img = Image.new("RGBA", (int(tw) + pad_x * 2, 62 + pad_y * 2), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.text((pad_x, pad_y), upper, font=font, fill=WHITE,
               stroke_width=stroke_w, stroke_fill=(0, 0, 0, 235))
    return img


# --- Assembly ------------------------------------------------------------

def _shot_clip(path: str, duration: float):
    return (
        ImageClip(path)
        .set_duration(duration)
        .fx(vfx.resize, lambda t: 1 + 0.03 * t)  # slight zoom-in per shot
        .set_position(("center", "center"))
    )


def build_video(player_name: str, from_club: str, to_club: str,
                 fee_text: str, from_logo_url: str | None,
                 to_logo_url: str | None, out_path: str,
                 transfer_id: int = 0) -> tuple[str, dict | None, str]:
    """Returns (out_path, photo_credit, music_credit). photo_credit is the
    Wikimedia Commons {title, url, license, artist} dict when a player photo
    was used as the background (None if the gradient fallback was used) -
    the caller should include it in the video's description, since
    CC-BY/CC-BY-SA require attribution. music_credit is always present."""
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    photo_credit = None
    player_photo = None
    try:
        photo_credit = player_image.find_best_photo(player_name)
        if photo_credit:
            player_photo = _download_photo(photo_credit["url"])
            if player_photo is None:
                print(f"Found a photo for {player_name} but failed to download it - using default background.")
                photo_credit = None
    except Exception as exc:  # noqa: BLE001
        print(f"Player photo lookup failed for {player_name}: {exc} - using default background.")
        photo_credit = None
        player_photo = None

    # Voiceover + word timings
    speech = f"{player_name} completes a move from {from_club} to {to_club}."
    if fee_text:
        speech += f" Transfer fee: {fee_text}."
    rate = TTS_RATE_VARIANTS[transfer_id % len(TTS_RATE_VARIANTS)]
    audio_path = out_path.replace(".mp4", "_audio.mp3")
    words = _synthesize_speech_with_words(speech, config.TTS_VOICE, rate, audio_path)

    voice_clip = AudioFileClip(audio_path)
    total_duration = max(6.0, voice_clip.duration + 1.0)

    # Shot timings: intro/outro get a proportional share (clamped), main
    # gets the rest. Padded by 2*SHOT_TRANSITION up front so that, after the
    # crossfades shrink the concatenated clip, the final video still lands
    # on total_duration (matching the audio) rather than running short.
    intro_duration = min(2.2, max(1.2, total_duration * 0.22))
    outro_duration = min(2.8, max(1.6, total_duration * 0.28))
    main_duration = max(1.2, (total_duration + 2 * SHOT_TRANSITION) - intro_duration - outro_duration)

    intro_frame = build_intro_frame(player_name, player_photo)
    main_frame = build_main_frame(player_name, from_club, to_club, from_logo_url, to_logo_url, player_photo)
    outro_frame = build_outro_frame(fee_text, player_photo)

    intro_path = out_path.replace(".mp4", "_intro.png")
    main_path = out_path.replace(".mp4", "_main.png")
    outro_path = out_path.replace(".mp4", "_outro.png")
    intro_frame.save(intro_path)
    main_frame.save(main_path)
    outro_frame.save(outro_path)

    shots = [
        _shot_clip(intro_path, intro_duration),
        _shot_clip(main_path, main_duration).crossfadein(SHOT_TRANSITION),
        _shot_clip(outro_path, outro_duration).crossfadein(SHOT_TRANSITION),
    ]
    shots_video = concatenate_videoclips(shots, padding=-SHOT_TRANSITION, method="compose")
    # Guards against float drift from the crossfade math above rather than
    # relying on it - actual duration should already match total_duration.
    shots_video = shots_video.set_duration(total_duration)

    # Captions - suppressed once the outro shot takes over, since it already
    # displays the fee (and CTA/badge) in the same lower-third the captions
    # would otherwise occupy; showing both is redundant and visually clashes.
    outro_start_time = total_duration - outro_duration
    caption_cutoff = max(0.0, outro_start_time - 0.3)

    caption_paths = []
    caption_clips = []
    for chunk in _group_captions(words, _sentence_word_counts(speech)):
        if chunk["start"] >= caption_cutoff:
            continue
        start = min(chunk["start"], max(0.0, total_duration - 0.1))
        end = min(chunk["end"], caption_cutoff, total_duration)
        duration = max(0.05, end - start)
        cap_img = _render_caption_image(chunk["text"])
        cap_path = out_path.replace(".mp4", f"_cap_{int(start * 1000)}.png")
        cap_img.save(cap_path)
        caption_paths.append(cap_path)
        caption_clips.append(
            ImageClip(cap_path)
            .set_start(start)
            .set_duration(duration)
            .set_position(("center", int(H * CAPTION_Y_FRACTION)))
        )

    # Music (rotates per transfer id so it's not the same track every time)
    music_track = config.MUSIC_TRACKS[transfer_id % len(config.MUSIC_TRACKS)]
    music_clip = audio_loop(AudioFileClip(music_track["path"]), duration=total_duration).fx(volumex, config.MUSIC_VOLUME)
    final_audio = CompositeAudioClip([music_clip, voice_clip]).set_duration(total_duration)

    final = CompositeVideoClip([shots_video, *caption_clips], size=(W, H)).set_audio(final_audio)
    final.write_videofile(out_path, fps=30, codec="libx264", audio_codec="aac",
                           threads=2, logger=None)

    final.close()
    shots_video.close()
    voice_clip.close()
    music_clip.close()
    for p in (intro_path, main_path, outro_path, audio_path, *caption_paths):
        try:
            os.remove(p)
        except OSError:
            pass

    return out_path, photo_credit, music_track["credit"]
