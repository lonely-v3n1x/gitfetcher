"""CLI entry: `gitfetcher <username>`."""

from __future__ import annotations

import httpx
from rich.console import Console
from typer import Argument, Option, Typer

from gitfetcher import __version__
from gitfetcher.github_client import (
    GithubNotFoundError,
    GithubRateLimitError,
    fetch_avatar_bytes,
    fetch_repo_stats,
    fetch_user,
    resolve_token,
)
from gitfetcher.image_backend import ImageBackend, detect_backend
from gitfetcher.models import RepoStats, normalize_login
from gitfetcher.render import print_neofetch

app = Typer(add_completion=False, help="Neofetch-like GitHub profile display for the terminal.")


def _version_callback(value: bool) -> None:
    if value:
        Console().print(f"gitfetcher {__version__}")
        raise SystemExit(0)


@app.command()
def main(
    username: str = Argument(..., help="GitHub username (e.g. torvalds)"),
    image: ImageBackend = Option(ImageBackend.AUTO, "--image", help="Image backend."),
    width: int = Option(32, "--width", min=16, max=48, help="Avatar width in cells."),
    token: str | None = Option(None, "--token", help="GitHub token (or GITHUB_TOKEN)."),
    no_stats: bool = Option(False, "--no-stats", help="Skip repo aggregation."),
    version: bool = Option(False, "--version", callback=_version_callback, help="Print version."),
) -> None:
    """Fetch a GitHub profile and display it neofetch-style."""
    console = Console()
    login = normalize_login(username)
    auth = resolve_token(token)
    try:
        user = fetch_user(login, auth)
        stats = RepoStats() if no_stats else fetch_repo_stats(login, auth)
        avatar = fetch_avatar_bytes(user.avatar_url, auth)
    except GithubNotFoundError as exc:
        console.print(f"[bold red]Error:[/] {exc}")
        raise SystemExit(1) from None
    except GithubRateLimitError as exc:
        console.print(f"[bold red]Error:[/] {exc} (set GITHUB_TOKEN)")
        raise SystemExit(1) from None
    except httpx.HTTPError as exc:
        console.print(f"[bold red]Network error:[/] {type(exc).__name__}")
        raise SystemExit(1) from None
    backend = detect_backend(image)
    print_neofetch(console, user, stats, avatar, backend, width)
