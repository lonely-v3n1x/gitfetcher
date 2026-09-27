"""Unit tests for parsing and backends."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from gitfetcher.image_backend import ImageBackend, detect_backend, iterm_sequence, kitty_sequence
from gitfetcher.models import GithubUser, RepoStats, normalize_login
from gitfetcher.render import _estimate_graphic_rows, _print_graphic_side_by_side, build_rows

if TYPE_CHECKING:
    from pytest import CaptureFixture


def test_normalize_login_strips_at() -> None:
    """Given: raw handle with @ / When: normalized / Then: lowercase login."""
    assert normalize_login("@Torvalds ") == "torvalds"


def test_github_user_parses_minimal() -> None:
    """Given: minimal API payload / When: validated / Then: typed user."""
    user = GithubUser.model_validate({"login": "octocat", "avatar_url": "https://x"})
    assert user.login == "octocat"
    assert user.followers == 0


def test_build_rows_skips_empty() -> None:
    """Given: user without optionals / When: rows built / Then: no empty rows."""
    user = GithubUser.model_validate({"login": "octocat"})
    labels = [r.label for r in build_rows(user, RepoStats())]
    assert "Followers" in labels
    assert "Company" not in labels


def test_kitty_sequence_framed() -> None:
    """Given: png bytes / When: kitty encoded / Then: pinned cursor, clean end."""
    seq = kitty_sequence(b"\x89PNG", width_cells=16)
    assert seq.startswith("\x1b_G")
    assert seq.endswith("\x1b\\")
    assert "C=1" in seq
    assert not seq.endswith("\n")


def test_iterm_sequence_framed() -> None:
    """Given: png bytes / When: iterm encoded / Then: OSC 1337 present."""
    assert "1337" in iterm_sequence(b"\x89PNG")


def test_detect_backend_auto_env() -> None:
    """Given: KITTY_WINDOW_ID set / When: auto resolved / Then: kitty."""
    os.environ["KITTY_WINDOW_ID"] = "1"
    try:
        assert detect_backend(ImageBackend.AUTO) == ImageBackend.KITTY
    finally:
        del os.environ["KITTY_WINDOW_ID"]


def test_graphic_overlay_anchors_left(capsys: CaptureFixture[str]) -> None:
    """Given: graphic backend / When: side-by-side rendered / Then: save+image+overlay."""
    from rich.console import Console
    from rich.text import Text

    console = Console(width=120)
    _print_graphic_side_by_side(
        console, b"fakepng", ImageBackend.KITTY, 24, [Text("Name: x")]
    )
    out = capsys.readouterr().out
    assert "\x1b7" in out
    assert "\x1b8" in out
    assert "C=1" in out
    assert "Name: x" in out
    assert "\x1b[28C" in out


def test_estimate_graphic_rows_scales() -> None:
    """Given: widths / When: estimated / Then: grows with width."""
    assert _estimate_graphic_rows(32) > _estimate_graphic_rows(16) > 0
