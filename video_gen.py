"""
Builds a short vertical (1080x1920) MP4 announcing a single transfer:
player name, "FROM -> TO" club crests, fee (if known), and a TTS voiceover.

Uses Pillow for the static frame and moviepy to add motion (simple zoom)
and audio.
"""
import os
import textwrap
import requests
from PIL import Image, ImageDraw, ImageFont
from gtts import gTTS
from moviepy.editor import ImageClip, AudioFileClip, CompositeVideoClip, vfx

W, H = 1080, 1920

# Bundled with most Linux systems / installed via apt in the workflow.
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_REGULAR = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

BG_TOP = (10, 20, 40)
BG_BOTTOM = (30, 60, 110)
ACCENT = (0, 200, 120)
WHITE = (255, 255, 255)


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
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        logo = Image.open(__import__("io").BytesIO(resp.content)).convert("RGBA")
        logo.thumbnail((size, size))
        return logo
    except Exception:
        return None


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
                 to_logo_url: str | None) -> Image.Image:
    img = _gradient_bg()
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
    draw.text(((W - tw) / 2, H - 100), footer, font=font_footer, fill=(180, 190, 200))

    return img


def build_video(player_name: str, from_club: str, to_club: str,
                 fee_text: str, from_logo_url: str | None,
                 to_logo_url: str | None, out_path: str) -> str:
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    frame_path = out_path.replace(".mp4", "_frame.png")
    frame = build_frame(player_name, from_club, to_club, fee_text,
                         from_logo_url, to_logo_url)
    frame.save(frame_path)

    # Voiceover
    speech = f"{player_name} has completed a transfer from {from_club} to {to_club}."
    if fee_text:
        speech += f" Fee: {fee_text}."
    audio_path = out_path.replace(".mp4", "_audio.mp3")
    gTTS(text=speech, lang="en").save(audio_path)

    audio_clip = AudioFileClip(audio_path)
    duration = max(6.0, audio_clip.duration + 1.5)

    image_clip = (
        ImageClip(frame_path)
        .set_duration(duration)
        .fx(vfx.resize, lambda t: 1 + 0.02 * t)  # slow zoom-in
        .set_position(("center", "center"))
    )
    video = CompositeVideoClip([image_clip], size=(W, H)).set_audio(audio_clip)
    video.write_videofile(out_path, fps=30, codec="libx264", audio_codec="aac",
                           threads=2, logger=None)

    video.close()
    audio_clip.close()
    os.remove(frame_path)
    os.remove(audio_path)
    return out_path
