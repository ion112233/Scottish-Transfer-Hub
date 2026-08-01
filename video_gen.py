"""
Builds a short vertical (1080x1920) MP4 announcing a single transfer:
player name, "FROM -> TO" club crests, fee (if known), and a TTS voiceover.

Uses Pillow for the static frame and moviepy to add motion (simple zoom)
and audio. Voiceover uses edge-tts (free neural voices, no API key) rather
than gTTS for a more natural sound.
"""
import asyncio
import io
import os

import edge_tts
import requests
from PIL import Image, ImageDraw, ImageFont

# moviepy 1.0.3's resize effect still calls Image.ANTIALIAS, which Pillow
# removed in v10. Restore it as an alias before moviepy needs it.
if not hasattr(Image, "ANTIALIAS"):
    Image.ANTIALIAS = Image.LANCZOS

from moviepy.editor import ImageClip, AudioFileClip, CompositeVideoClip, CompositeAudioClip, vfx
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
    the top (behind the header/player name) and bottom (behind the crests,
    fee and footer), lightly through the middle - so the overlaid text and
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


def build_frame(player_name: str, from_club: str, to_club: str,
                 fee_text: str, from_logo_url: str | None,
                 to_logo_url: str | None,
                 player_photo: Image.Image | None = None) -> Image.Image:
    img = _photo_bg(player_photo) if player_photo is not None else _gradient_bg()
    draw = ImageDraw.Draw(img)

    font_title = ImageFont.truetype(FONT_BOLD, 64)
    font_player = ImageFont.truetype(FONT_BOLD, 90)
    font_club = ImageFont.truetype(FONT_REGULAR, 48)
    font_fee = ImageFont.truetype(FONT_BOLD, 56)
    font_arrow = ImageFont.truetype(FONT_BOLD, 90)

    # Header
    header = "TRANSFER CONFIRMED"
    tw = draw.textlength(header, font=font_title)
    draw.text(((W - tw) / 2, 140), header, font=font_title, fill=ACCENT)

    # Player name (wrapped, centered)
    lines = _wrapped_text(draw, player_name.upper(), font_player, W - 120)
    y = 300
    for line in lines:
        tw = draw.textlength(line, font=font_player)
        draw.text(((W - tw) / 2, y), line, font=font_player, fill=WHITE)
        y += 100

    # Club crests + arrow
    logo_y = y + 80
    from_logo = _download_logo(from_logo_url)
    to_logo = _download_logo(to_logo_url)

    left_x = W // 4
    right_x = 3 * W // 4

    if from_logo:
        img.paste(from_logo, (left_x - from_logo.width // 2, logo_y), from_logo)
    if to_logo:
        img.paste(to_logo, (right_x - to_logo.width // 2, logo_y), to_logo)

    arrow_y = logo_y + 100
    draw.text((W // 2 - 30, arrow_y), "→", font=font_arrow, fill=ACCENT)

    # Club names
    name_y = logo_y + 280
    for club, cx in ((from_club, left_x), (to_club, right_x)):
        cl = _wrapped_text(draw, club, font_club, W // 2 - 40)
        yy = name_y
        for line in cl:
            tw = draw.textlength(line, font=font_club)
            draw.text((cx - tw / 2, yy), line, font=font_club, fill=WHITE)
            yy += 56

    # Fee
    if fee_text:
        tw = draw.textlength(fee_text, font=font_fee)
        draw.text(((W - tw) / 2, H - 260), fee_text, font=font_fee, fill=ACCENT)

    # Footer
    footer = "Scottish Football Transfers"
    font_footer = ImageFont.truetype(FONT_REGULAR, 36)
    tw = draw.textlength(footer, font=font_footer)
    draw.text(((W - tw) / 2, H - 100), footer, font=font_footer, fill=(210, 190, 220))

    return img


def _synthesize_speech(text: str, out_path: str) -> None:
    async def _run():
        communicate = edge_tts.Communicate(text, config.TTS_VOICE)
        await communicate.save(out_path)

    asyncio.run(_run())


def build_video(player_name: str, from_club: str, to_club: str,
                 fee_text: str, from_logo_url: str | None,
                 to_logo_url: str | None, out_path: str) -> tuple[str, dict | None]:
    """Returns (out_path, photo_credit). photo_credit is the Wikimedia
    Commons {title, url, license, artist} dict when a player photo was used
    as the background (None if the default gradient background was used
    instead) - the caller should include it in the video's description,
    since CC-BY/CC-BY-SA require attribution."""
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

    frame_path = out_path.replace(".mp4", "_frame.png")
    frame = build_frame(player_name, from_club, to_club, fee_text,
                         from_logo_url, to_logo_url, player_photo)
    frame.save(frame_path)

    # Voiceover
    speech = f"{player_name} has completed a transfer from {from_club} to {to_club}."
    if fee_text:
        speech += f" Fee: {fee_text}."
    audio_path = out_path.replace(".mp4", "_audio.mp3")
    _synthesize_speech(speech, audio_path)

    voice_clip = AudioFileClip(audio_path)
    duration = max(6.0, voice_clip.duration + 1.5)

    music_clip = None
    final_audio = voice_clip
    if os.path.exists(config.MUSIC_PATH):
        # audio_loop trims if duration <= the track's own length (56s, well
        # over any clip we make) and loops if it's ever somehow longer.
        music_clip = audio_loop(AudioFileClip(config.MUSIC_PATH), duration=duration).fx(volumex, config.MUSIC_VOLUME)
        final_audio = CompositeAudioClip([music_clip, voice_clip]).set_duration(duration)

    image_clip = (
        ImageClip(frame_path)
        .set_duration(duration)
        .fx(vfx.resize, lambda t: 1 + 0.02 * t)  # slow zoom-in
        .set_position(("center", "center"))
    )
    video = CompositeVideoClip([image_clip], size=(W, H)).set_audio(final_audio)
    video.write_videofile(out_path, fps=30, codec="libx264", audio_codec="aac",
                           threads=2, logger=None)

    video.close()
    voice_clip.close()
    if music_clip is not None:
        music_clip.close()
    os.remove(frame_path)
    os.remove(audio_path)
    return out_path, photo_credit
