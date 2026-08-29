from __future__ import annotations

import random
import textwrap
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont, ImageOps


# ============================================================
# Fonts
# ============================================================

def _font(size: int):
    size = max(16, int(size))

    paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
    ]

    for path in paths:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass

    return ImageFont.load_default()


# ============================================================
# Text drawing
# ============================================================

def _draw_centered_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    y: int,
    width: int,
    size: int,
):
    if not text:
        return

    font = _font(size)

    words = text.split()
    lines = []
    current = ""

    for word in words:
        test = f"{current} {word}".strip()

        try:
            box = draw.textbbox(
                (0, 0),
                test,
                font=font,
                stroke_width=2,
            )
            test_width = box[2] - box[0]
        except Exception:
            test_width = len(test) * size // 2

        if test_width <= width - 40:
            current = test
        else:
            if current:
                lines.append(current)
            current = word

    if current:
        lines.append(current)

    line_height = size + 8

    for i, line in enumerate(lines[:6]):
        try:
            box = draw.textbbox(
                (0, 0),
                line,
                font=font,
                stroke_width=3,
            )
            text_width = box[2] - box[0]
        except Exception:
            text_width = len(line) * size // 2

        x = (width - text_width) // 2

        draw.text(
            (x, y + i * line_height),
            line,
            font=font,
            fill="white",
            stroke_width=3,
            stroke_fill="black",
        )


# ============================================================
# Classic meme
# ============================================================

def _classic(im: Image.Image, caption: str) -> Image.Image:
    out = im.copy()

    draw = ImageDraw.Draw(out)

    size = max(
        22,
        min(64, out.width // 14),
    )

    _draw_centered_text(
        draw,
        caption[:250],
        15,
        out.width,
        size,
    )

    return out


# ============================================================
# Top / bottom meme
# ============================================================

def _top_bottom(
    im: Image.Image,
    caption: str,
) -> Image.Image:
    out = im.copy()

    draw = ImageDraw.Draw(out)

    parts = [
        x.strip()
        for x in caption.split("\n")
        if x.strip()
    ]

    if len(parts) >= 2:
        top = parts[0]
        bottom = parts[1]
    else:
        words = caption.split()

        middle = max(
            1,
            len(words) // 2,
        )

        top = " ".join(words[:middle])
        bottom = " ".join(words[middle:])

    size = max(
        22,
        min(62, out.width // 15),
    )

    _draw_centered_text(
        draw,
        top[:120],
        15,
        out.width,
        size,
    )

    bottom_font = _font(size)

    try:
        box = draw.textbbox(
            (0, 0),
            bottom[:120],
            font=bottom_font,
            stroke_width=3,
        )
        height = box[3] - box[1]
    except Exception:
        height = size

    _draw_centered_text(
        draw,
        bottom[:120],
        max(15, out.height - height * 3),
        out.width,
        size,
    )

    return out


# ============================================================
# Bottom caption band
# ============================================================

def _bottom_band(
    im: Image.Image,
    caption: str,
) -> Image.Image:
    band = max(
        90,
        int(im.height * 0.22),
    )

    canvas = Image.new(
        "RGB",
        (
            im.width,
            im.height + band,
        ),
        "black",
    )

    canvas.paste(
        im,
        (0, 0),
    )

    draw = ImageDraw.Draw(canvas)

    _draw_centered_text(
        draw,
        caption[:250],
        im.height + 15,
        im.width,
        max(20, im.width // 24),
    )

    return canvas


# ============================================================
# Reaction meme
# ============================================================

def _reaction(
    im: Image.Image,
    caption: str,
) -> Image.Image:
    out = im.copy()

    draw = ImageDraw.Draw(out)

    # Slightly different placement from normal memes.
    size = max(
        20,
        min(58, out.width // 17),
    )

    wrapped = textwrap.fill(
        caption[:180],
        width=24,
    )

    try:
        box = draw.multiline_textbbox(
            (0, 0),
            wrapped,
            font=_font(size),
            stroke_width=3,
        )

        tw = box[2] - box[0]
        th = box[3] - box[1]
    except Exception:
        tw = out.width // 2
        th = size * 2

    x = max(
        10,
        out.width - tw - 25,
    )

    y = max(
        10,
        out.height - th - 25,
    )

    draw.multiline_text(
        (x, y),
        wrapped,
        font=_font(size),
        fill="white",
        stroke_width=3,
        stroke_fill="black",
        spacing=5,
    )

    return out


# ============================================================
# Impact meme
# ============================================================

def _impact(
    im: Image.Image,
    caption: str,
) -> Image.Image:
    out = ImageOps.autocontrast(
        im.copy()
    )

    draw = ImageDraw.Draw(out)

    size = max(
        24,
        min(72, out.width // 12),
    )

    _draw_centered_text(
        draw,
        caption[:160].upper(),
        20,
        out.width,
        size,
    )

    return out


# ============================================================
# Random meme style
# ============================================================

MEME_STYLES = (
    "classic",
    "top_bottom",
    "bottom_band",
    "reaction",
    "impact",
)


def make_meme(
    raw: bytes,
    caption: str,
    style: str | None = None,
) -> BytesIO:
    im = Image.open(
        BytesIO(raw)
    ).convert("RGB")

    # Keep processing lightweight.
    im.thumbnail(
        (1600, 1600),
        Image.Resampling.LANCZOS,
    )

    if not caption:
        caption = "me fr"

    selected = (
        style
        if style in MEME_STYLES
        else random.choice(MEME_STYLES)
    )

    if selected == "classic":
        out = _classic(
            im,
            caption,
        )

    elif selected == "top_bottom":
        out = _top_bottom(
            im,
            caption,
        )

    elif selected == "bottom_band":
        out = _bottom_band(
            im,
            caption,
        )

    elif selected == "reaction":
        out = _reaction(
            im,
            caption,
        )

    elif selected == "impact":
        out = _impact(
            im,
            caption,
        )

    else:
        out = _classic(
            im,
            caption,
        )

    result = BytesIO()

    result.name = "lmyrfawya_meme.jpg"

    out.save(
        result,
        "JPEG",
        quality=86,
        optimize=True,
    )

    result.seek(0)

    return result


# ============================================================
# Existing API used by handlers.py
# ============================================================

def caption_meme(
    raw: bytes,
    caption: str,
) -> BytesIO:
    """
    Backwards-compatible wrapper.

    handlers.py can continue calling:

        caption_meme(raw, caption)

    while the actual meme style is randomized.
    """

    return make_meme(
        raw,
        caption,
        style=None,
    )


# ============================================================
# Explicit random meme
# ============================================================

def random_meme(
    raw: bytes,
    caption: str,
) -> BytesIO:
    return make_meme(
        raw,
        caption,
        style=random.choice(MEME_STYLES),
    )


# ============================================================
# Two-image meme / mashup
# ============================================================

def meme_mashup(
    raw_a: bytes,
    raw_b: bytes,
    caption: str = "",
) -> BytesIO:
    a = Image.open(
        BytesIO(raw_a)
    ).convert("RGB")

    b = Image.open(
        BytesIO(raw_b)
    ).convert("RGB")

    width = max(
        a.width,
        b.width,
    )

    height = a.height + b.height

    canvas = Image.new(
        "RGB",
        (width, height),
        "black",
    )

    canvas.paste(
        a,
        (
            (width - a.width) // 2,
            0,
        ),
    )

    canvas.paste(
        b,
        (
            (width - b.width) // 2,
            a.height,
        ),
    )

    if caption:
        draw = ImageDraw.Draw(canvas)

        _draw_centered_text(
            draw,
            caption[:180],
            10,
            width,
            max(20, width // 25),
        )

    result = BytesIO()

    result.name = "lmyrfawya_mashup.jpg"

    canvas.save(
        result,
        "JPEG",
        quality=84,
        optimize=True,
    )

    result.seek(0)

    return result