"""
Generates premium, themed UPI payment QR cards as PNG images.

Fonts are bundled inside /fonts so rendering is identical on every
platform (local dev, Vercel, any VPS) instead of depending on system
fonts that may not exist in a minimal serverless container.
"""

import io
import os
import random
from typing import Optional

import qrcode
from PIL import Image, ImageDraw, ImageFont
from qrcode.image.styledpil import StyledPilImage
from qrcode.image.styles.moduledrawers import RoundedModuleDrawer

FONT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "fonts")
FONT_BOLD = os.path.join(FONT_DIR, "DejaVuSansMono-Bold.ttf")
FONT_BOLD_ITALIC = os.path.join(FONT_DIR, "DejaVuSansMono-BoldOblique.ttf")

WATERMARK_TEXT = "Made by Euthle"

# ─── Themes ──────────────────────────────────────────────────────────────────
THEMES = [
    {
        "name": "neon_green",
        "bg": (8, 10, 8),
        "border": (0, 255, 100),
        "text": (0, 255, 100),
        "dim_text": (0, 180, 70),
        "qr_fill": (0, 240, 90),
        "qr_back": (8, 10, 8),
    },
    {
        "name": "cyber_blue",
        "bg": (5, 8, 20),
        "border": (0, 180, 255),
        "text": (255, 255, 255),
        "dim_text": (100, 180, 255),
        "qr_fill": (0, 180, 255),
        "qr_back": (5, 8, 20),
    },
    {
        "name": "gold_premium",
        "bg": (10, 8, 2),
        "border": (212, 175, 55),
        "text": (255, 215, 0),
        "dim_text": (180, 145, 30),
        "qr_fill": (212, 175, 55),
        "qr_back": (10, 8, 2),
    },
    {
        "name": "purple_galaxy",
        "bg": (8, 2, 18),
        "border": (180, 50, 255),
        "text": (220, 150, 255),
        "dim_text": (140, 80, 200),
        "qr_fill": (180, 50, 255),
        "qr_back": (8, 2, 18),
    },
    {
        "name": "red_alert",
        "bg": (12, 2, 2),
        "border": (255, 40, 40),
        "text": (255, 255, 255),
        "dim_text": (200, 80, 80),
        "qr_fill": (255, 40, 40),
        "qr_back": (12, 2, 2),
    },
]

_font_cache: dict = {}


def _font(size: int, italic: bool = False) -> ImageFont.FreeTypeFont:
    """Load a bundled bold (or bold-italic) font at the given size, cached."""
    key = (size, italic)
    if key in _font_cache:
        return _font_cache[key]
    path = FONT_BOLD_ITALIC if italic else FONT_BOLD
    try:
        font = ImageFont.truetype(path, size)
    except (IOError, OSError):
        # Bundled font missing for some reason — fall back gracefully
        # instead of crashing the whole request.
        font = ImageFont.load_default()
    _font_cache[key] = font
    return font


def _circle_crop(img: Image.Image, size: int) -> Image.Image:
    """Crop image to a circle."""
    img = img.resize((size, size), Image.LANCZOS).convert("RGBA")
    mask = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0, size, size), fill=255)
    result = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    result.paste(img, (0, 0), mask)
    return result


def _draw_glow_rect(draw, x0, y0, x1, y1, color, width=3, glow_passes=4):
    """Draw a glowing rectangle border."""
    r, g, b = color
    for i in range(glow_passes, 0, -1):
        alpha = int(60 * (i / glow_passes))
        pad = i * 2
        draw.rectangle(
            [x0 - pad, y0 - pad, x1 + pad, y1 + pad],
            outline=(r, g, b, alpha),
            width=1,
        )
    draw.rectangle([x0, y0, x1, y1], outline=color, width=width)


def _centered_text(draw, y, text, font, fill, card_w):
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    draw.text(((card_w - tw) // 2, y), text, fill=fill, font=font)


def generate_qr_image(
    upi_id: str,
    display_name: str,
    amount: str,
    hide_upi: bool = True,
    profile_photo_bytes: Optional[bytes] = None,
    bot_username: str = "UpiQrGenBot",
    theme: Optional[dict] = None,
) -> bytes:
    """Generate a premium UPI QR card image and return PNG bytes."""

    if theme is None:
        theme = random.choice(THEMES)

    bg_color = theme["bg"]
    border_color = theme["border"]
    text_color = theme["text"]
    dim_color = theme["dim_text"]
    qr_fill = theme["qr_fill"]
    qr_back = theme["qr_back"]

    # ── Build UPI deep-link string ────────────────────────────────────────────
    upi_string = f"upi://pay?pa={upi_id}&pn={display_name}&am={amount}&cu=INR"

    # ── Generate raw QR ───────────────────────────────────────────────────────
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=1,
    )
    qr.add_data(upi_string)
    qr.make(fit=True)

    try:
        qr_img = qr.make_image(
            image_factory=StyledPilImage,
            module_drawer=RoundedModuleDrawer(),
            fill_color=qr_fill,
            back_color=qr_back,
        ).convert("RGBA")
    except Exception:
        qr_img = qr.make_image(fill_color=qr_fill, back_color=qr_back).convert("RGBA")

    qr_size = 400
    qr_img = qr_img.resize((qr_size, qr_size), Image.LANCZOS)

    # ── Canvas ────────────────────────────────────────────────────────────────
    card_w, card_h = 520, 720
    canvas = Image.new("RGBA", (card_w, card_h), (*bg_color, 255))
    draw = ImageDraw.Draw(canvas, "RGBA")

    # Subtle grid pattern
    for x in range(0, card_w, 30):
        draw.line([(x, 0), (x, card_h)], fill=(*border_color, 12), width=1)
    for y in range(0, card_h, 30):
        draw.line([(0, y), (card_w, y)], fill=(*border_color, 12), width=1)

    # Outer glow border
    _draw_glow_rect(draw, 10, 10, card_w - 10, card_h - 10, border_color, width=2, glow_passes=5)

    # ── Fonts (bold everywhere, italic for secondary/supporting text) ────────
    font_header = _font(13)
    font_amount = _font(22)
    font_label = _font(11, italic=True)
    font_footer = _font(10, italic=True)
    font_watermark = _font(9, italic=True)

    # ── Header ────────────────────────────────────────────────────────────────
    _centered_text(draw, 32, "INITIALIZE PAYMENT", font_header, border_color, card_w)
    draw.line([(40, 54), (card_w - 40, 54)], fill=(*border_color, 120), width=1)

    # ── Amount ────────────────────────────────────────────────────────────────
    amount_text = f"AMT // {amount} INR"
    _centered_text(draw, 64, amount_text, font_amount, text_color, card_w)

    # ── QR Image ─────────────────────────────────────────────────────────────
    qr_x = (card_w - qr_size) // 2
    qr_y = 108
    canvas.paste(qr_img, (qr_x, qr_y), qr_img)

    # Glow frame around QR
    _draw_glow_rect(
        draw,
        qr_x - 8, qr_y - 8,
        qr_x + qr_size + 8, qr_y + qr_size + 8,
        border_color, width=2, glow_passes=4,
    )

    # ── Profile Photo overlay (center of QR) ─────────────────────────────────
    logo_size = 64
    if profile_photo_bytes:
        try:
            pfp = Image.open(io.BytesIO(profile_photo_bytes))
            logo = _circle_crop(pfp, logo_size)
            ring_size = logo_size + 6
            ring = Image.new("RGBA", (ring_size, ring_size), (0, 0, 0, 0))
            ring_draw = ImageDraw.Draw(ring)
            ring_draw.ellipse((0, 0, ring_size, ring_size), fill=(255, 255, 255, 255))
            logo_x = qr_x + (qr_size - ring_size) // 2
            logo_y = qr_y + (qr_size - ring_size) // 2
            canvas.paste(ring, (logo_x, logo_y), ring)
            canvas.paste(logo, (logo_x + 3, logo_y + 3), logo)
        except Exception:
            pass

    # ── Footer ────────────────────────────────────────────────────────────────
    footer_y = qr_y + qr_size + 20
    draw.line([(40, footer_y), (card_w - 40, footer_y)], fill=(*border_color, 120), width=1)
    footer_y += 12

    paying_to = f"PAYING TO: {'HIDDEN' if hide_upi else upi_id.upper()}"
    _centered_text(draw, footer_y, paying_to, font_label, dim_color, card_w)

    sub_text = "Scan with any UPI app to proceed"
    _centered_text(draw, footer_y + 20, sub_text, font_footer, (*text_color, 160), card_w)

    bot_credit = f"Generated by @{bot_username}"
    _centered_text(draw, card_h - 44, bot_credit, font_watermark, (*border_color, 130), card_w)

    # "Made by Euthle" watermark — always present on every generated card
    _centered_text(draw, card_h - 26, WATERMARK_TEXT, font_watermark, (*dim_color, 160), card_w)

    # Corner accents
    accent_len = 18
    corners = [
        (18, 18, 18 + accent_len, 18, 18, 18 + accent_len),
        (card_w - 18, 18, card_w - 18 - accent_len, 18, card_w - 18, 18 + accent_len),
        (18, card_h - 18, 18 + accent_len, card_h - 18, 18, card_h - 18 - accent_len),
        (card_w - 18, card_h - 18, card_w - 18 - accent_len, card_h - 18, card_w - 18, card_h - 18 - accent_len),
    ]
    for cx, cy, ex1, ey1, ex2, ey2 in corners:
        draw.line([(cx, cy), (ex1, ey1)], fill=border_color, width=2)
        draw.line([(cx, cy), (ex2, ey2)], fill=border_color, width=2)

    # ── Export ────────────────────────────────────────────────────────────────
    buf = io.BytesIO()
    canvas.convert("RGB").save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf.read()
