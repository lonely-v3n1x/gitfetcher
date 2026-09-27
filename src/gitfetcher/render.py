"""Neofetch-style side-by-side layout with rich."""

from __future__ import annotations

import sys
from dataclasses import dataclass

from rich.console import Console
from rich.text import Text

from gitfetcher.image_backend import ImageBackend, ascii_halfblock, emit_graphic, to_square_png
from gitfetcher.models import GithubUser, RepoStats

_ACCENT = "bold cyan"
_LABEL = "bold green"


@dataclass(frozen=True, slots=True)
class InfoRow:
    """Single label/value line in the right-hand info panel."""

    label: str
    value: str


def build_rows(user: GithubUser, stats: RepoStats) -> list[InfoRow]:
    """Build display rows, skipping empty optional fields."""
    display_name = user.name or user.login
    rows: list[InfoRow] = [
        InfoRow(label="Name", value=display_name),
        InfoRow(label="Login", value=f"@{user.login}"),
    ]
    if user.bio:
        rows.append(InfoRow(label="Bio", value=user.bio))
    if user.company:
        rows.append(InfoRow(label="Company", value=user.company))
    if user.location:
        rows.append(InfoRow(label="Location", value=user.location))
    if user.blog:
        rows.append(InfoRow(label="Blog", value=user.blog))
    if user.twitter_username:
        rows.append(InfoRow(label="Twitter", value=f"@{user.twitter_username}"))
    rows.extend(
        [
            InfoRow(label="Followers", value=str(user.followers)),
            InfoRow(label="Following", value=str(user.following)),
            InfoRow(label="Repos", value=str(user.public_repos)),
            InfoRow(label="Gists", value=str(user.public_gists)),
            InfoRow(label="Stars", value=str(stats.stars)),
            InfoRow(label="Forks", value=str(stats.forks)),
        ]
    )
    if stats.top_languages:
        rows.append(InfoRow(label="Languages", value=", ".join(stats.top_languages)))
    if user.created_at is not None:
        rows.append(InfoRow(label="Created", value=user.created_at.strftime("%Y-%m-%d")))
    return rows


def _print_header(console: Console, user: GithubUser) -> None:
    title = Text(f"{user.name or user.login}@{user.login}", style=_ACCENT)
    console.print(title)
    console.print(Text("-" * len(title.plain), style="dim"))


def _print_rows(console: Console, rows: list[InfoRow]) -> None:
    for row in rows:
        console.print(f"[{_LABEL}]{row.label}[/]: {row.value}")


def _right_panel(user: GithubUser, stats: RepoStats) -> list[Text]:
    """Info panel lines shared by graphic and ASCII side-by-side modes."""
    header = Text(f"{user.name or user.login}@{user.login}", style=_ACCENT)
    lines: list[Text] = [header, Text("-" * len(header.plain), style="dim")]
    for row in build_rows(user, stats):
        lines.append(Text.from_markup(f"[{_LABEL}]{row.label}[/]: {row.value}"))
    return lines


def _estimate_graphic_rows(width_cells: int) -> int:
    """Terminal rows a square avatar occupies at the given width."""
    return max(8, width_cells // 2 + 1)


def _print_graphic_side_by_side(
    console: Console,
    png: bytes,
    backend: ImageBackend,
    width_cells: int,
    right: list[Text],
) -> None:
    """Anchor the avatar left, overlay the info panel on its right.

    Uses cursor save/restore so the graphic stays in the left column
    while text prints in the right column, neofetch-style.
    """
    image_rows = _estimate_graphic_rows(width_cells)
    # Kitty sequence carries C=1 so the cursor never moves on placement;
    # ESC 7/8 is backup for terminals that ignore C=1 but honor restore.
    # (CSI s/u must not be used: kitty ignores it.)
    sys.stdout.write("\x1b7")
    sys.stdout.flush()
    emit_graphic(png, backend, width_cells)
    sys.stdout.flush()
    sys.stdout.write("\x1b8")
    gap = width_cells + 4
    for line in right:
        sys.stdout.write(f"\x1b[{gap}C")
        sys.stdout.flush()
        console.print(line, soft_wrap=True, crop=False)
    for _ in range(image_rows - len(right)):
        console.print("")
    console.print("")


def _print_columns(
    console: Console, left: list[str], right: list[Text], width_cells: int
) -> None:
    """True side-by-side columns for the ASCII path."""
    height = max(len(left), len(right))
    left = [*left, *[" " * width_cells] * (height - len(left))]
    right = [*right, *[Text("") for _ in range(height - len(right))]]
    for lline, rline in zip(left, right, strict=True):
        sys.stdout.write(f"{lline}  ")
        console.print(rline, soft_wrap=True, crop=False)


def print_neofetch(
    console: Console,
    user: GithubUser,
    stats: RepoStats,
    avatar_raw: bytes | None,
    backend: ImageBackend,
    width_cells: int = 32,
) -> None:
    """Render avatar + info side-by-side, neofetch-style.

    Graphic backends anchor the avatar in the left column and overlay
    the info panel on the right. ASCII draws half-block art on the left.
    """
    match backend:
        case ImageBackend.KITTY | ImageBackend.ITERM:
            png = to_square_png(avatar_raw) if avatar_raw is not None else None
            if png is None or not sys.stdout.isatty():
                left = ascii_halfblock(avatar_raw, width_cells) if avatar_raw else []
                right_text = _right_panel(user, stats)
                _print_columns(console, left, right_text, width_cells)
                return
            _print_graphic_side_by_side(console, png, backend, width_cells, _right_panel(user, stats))
        case ImageBackend.ASCII | ImageBackend.AUTO:
            left = ascii_halfblock(avatar_raw, width_cells) if avatar_raw else []
            _print_columns(console, left, _right_panel(user, stats), width_cells)
        case ImageBackend.NONE:
            _print_header(console, user)
            _print_rows(console, build_rows(user, stats))
        case _:
            _print_header(console, user)
            _print_rows(console, build_rows(user, stats))
