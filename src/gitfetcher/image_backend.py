"""Terminal image backends: kitty, iterm2, ascii fallback."""

from __future__ import annotations

import base64
import io
import os
import sys
from enum import StrEnum
from typing import assert_never


class ImageBackend(StrEnum):
    """Supported terminal image protocols."""

    AUTO = "auto"
    KITTY = "kitty"
    ITERM = "iterm"
    ASCII = "ascii"
    NONE = "none"


def detect_backend(preference: ImageBackend) -> ImageBackend:
    """Resolve AUTO to a concrete backend from environment."""
    match preference:
        case ImageBackend.AUTO:
            if os.environ.get("KITTY_WINDOW_ID"):
                return ImageBackend.KITTY
            term = os.environ.get("TERM", "")
            term_program = os.environ.get("TERM_PROGRAM", "")
            if os.environ.get("ITERM_SESSION_ID") or term_program in {"iTerm.app", "WezTerm"}:
                return ImageBackend.ITERM
            if "kitty" in term:
                return ImageBackend.KITTY
            return ImageBackend.ASCII
        case ImageBackend.KITTY:
            return ImageBackend.KITTY
        case ImageBackend.ITERM:
            return ImageBackend.ITERM
        case ImageBackend.ASCII:
            return ImageBackend.ASCII
        case ImageBackend.NONE:
            return ImageBackend.NONE
        case _ as unreachable:
            assert_never(unreachable)


def kitty_sequence(png_bytes: bytes, width_cells: int = 32) -> str:
    """Build a Kitty graphics protocol escape sequence for PNG bytes.

    C=1 pins the cursor (spec: no movement on placement), so callers can
    overlay text beside the image from a known position. No trailing
    newline is emitted — anything moving the cursor breaks the overlay.
    """
    b64 = base64.b64encode(png_bytes).decode("ascii")
    chunks: list[str] = [b64[i : i + 4096] for i in range(0, len(b64), 4096)]
    parts: list[str] = []
    for idx, chunk in enumerate(chunks):
        more = 1 if idx < len(chunks) - 1 else 0
        if idx == 0:
            parts.append(f"\x1b_Gf=100,a=T,c={width_cells},C=1,m={more};{chunk}\x1b\\")
        else:
            parts.append(f"\x1b_Gm={more};{chunk}\x1b\\")
    return "".join(parts)


def iterm_sequence(png_bytes: bytes, width_cells: int = 32) -> str:
    """Build an iTerm2 inline-image escape sequence for PNG bytes."""
    b64 = base64.b64encode(png_bytes).decode("ascii")
    width_px = width_cells * 8
    return f"\x1b]1337;File=inline=1;width={width_px}px;preserveAspectRatio=1:{b64}\x07\n"


def _load_image(raw: bytes) -> tuple[list[list[tuple[int, int, int]]], int, int] | None:
    """Decode bytes to RGB rows via Pillow; None if Pillow/mime missing."""
    try:
        from PIL import Image  # type: ignore[import-not-found]
    except ImportError:
        return None
    try:
        with Image.open(io.BytesIO(raw)) as img:
            rgb = img.convert("RGB")
            w, h = rgb.size
            pixels = list(rgb.getdata())
    except (OSError, ValueError):
        return None
    rows: list[list[tuple[int, int, int]]] = []
    it = iter(pixels)
    for _ in range(h):
        rows.append([(r, g, b) for r, g, b in (next(it) for _ in range(w))])
    return rows, w, h


def to_square_png(raw: bytes, size: int = 320) -> bytes | None:
    """Center-crop avatar bytes to square PNG; None when undecodable."""
    try:
        from PIL import Image  # type: ignore[import-not-found]
    except ImportError:
        return None
    try:
        with Image.open(io.BytesIO(raw)) as img:
            rgb = img.convert("RGB")
            w, h = rgb.size
            side = min(w, h)
            left = (w - side) // 2
            top = (h - side) // 2
            cropped = rgb.crop((left, top, left + side, top + side))
            out = cropped.resize((size, size))
            buf = io.BytesIO()
            out.save(buf, format="PNG")
            return buf.getvalue()
    except (OSError, ValueError):
        return None


def ascii_halfblock(raw: bytes, width_cells: int = 32) -> list[str]:
    """Render image as ANSI half-block rows (2 pixels per cell)."""
    decoded = _load_image(raw)
    if decoded is None:
        return [ "(no image: install pillow for avatar)" ]
    rows, w, h = decoded
    target_w = max(8, min(width_cells, 48))
    target_h = max(4, int(target_w * h / w / 2))
    # Nearest-neighbor downsample.
    sampled: list[list[tuple[int, int, int]]] = []
    for y in range(target_h * 2):
        src_y = min(h - 1, int(y * h / (target_h * 2)))
        line: list[tuple[int, int, int]] = []
        for x in range(target_w):
            src_x = min(w - 1, int(x * w / target_w))
            line.append(rows[src_y][src_x])
        sampled.append(line)
    out: list[str] = []
    for y in range(0, len(sampled) - 1, 2):
        top = sampled[y]
        bottom = sampled[y + 1]
        cells: list[str] = []
        for (rt, gt, bt), (rb, gb, bb) in zip(top, bottom, strict=True):
            cells.append(f"\x1b[38;2;{rt};{gt};{bt}m\x1b[48;2;{rb};{gb};{bb}m▀")
        cells.append("\x1b[0m")
        out.append("".join(cells))
    return out


def emit_graphic(png_bytes: bytes, backend: ImageBackend, width_cells: int) -> None:
    """Write the graphic escape sequence to stdout."""
    match backend:
        case ImageBackend.KITTY:
            sys.stdout.write(kitty_sequence(png_bytes, width_cells))
        case ImageBackend.ITERM:
            sys.stdout.write(iterm_sequence(png_bytes, width_cells))
        case ImageBackend.ASCII | ImageBackend.NONE | ImageBackend.AUTO:
            # ASCII/NONE handled by caller line layout; nothing to emit here.
            return
        case _ as unreachable:
            assert_never(unreachable)
