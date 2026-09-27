"""GitHub API client with production httpx defaults."""

from __future__ import annotations

import os
import socket
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass

import httpx

from gitfetcher.models import GithubLogin, GithubRepo, GithubUser, RepoStats

_LIMITS = httpx.Limits(
    max_connections=200,
    max_keepalive_connections=40,
    keepalive_expiry=30.0,
)

_TIMEOUT = httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=10.0)

_SOCKET_OPTIONS: list[tuple[int, int, int]] = [
    (socket.IPPROTO_TCP, socket.TCP_NODELAY, 1),
]

_API_BASE = "https://api.github.com"


@dataclass(frozen=True, slots=True)
class GithubNotFoundError(Exception):
    """Raised when the GitHub user does not exist."""

    login: str

    def __str__(self) -> str:
        return f"github user '{self.login}' not found"


@dataclass(frozen=True, slots=True)
class GithubRateLimitError(Exception):
    """Raised when the GitHub API rate limit is exhausted."""

    detail: str = "rate limit exceeded"

    def __str__(self) -> str:
        return f"github API rate limit exceeded: {self.detail}"


def _default_headers(token: str | None) -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "gitfetcher/0.1.0",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def create_client(token: str | None = None) -> httpx.Client:
    """Create a tuned sync httpx client."""
    transport = httpx.HTTPTransport(
        http2=True,
        retries=3,
        limits=_LIMITS,
        socket_options=_SOCKET_OPTIONS,  # type: ignore[arg-type]
    )
    return httpx.Client(
        transport=transport,
        timeout=_TIMEOUT,
        base_url=_API_BASE,
        headers=_default_headers(token),
        follow_redirects=True,
    )


def resolve_token(explicit: str | None) -> str | None:
    """Prefer explicit token, fall back to GITHUB_TOKEN env."""
    if explicit:
        return explicit
    return os.environ.get("GITHUB_TOKEN")


def fetch_user(login: GithubLogin, token: str | None = None) -> GithubUser:
    """Fetch and parse GET /users/{login}."""
    with create_client(token) as client:
        resp = client.get(f"/users/{login}")
        if resp.status_code == 404:
            raise GithubNotFoundError(login=str(login))
        if resp.status_code == 403 and "rate limit" in resp.text.lower():
            raise GithubRateLimitError(detail=resp.text[:200])
        resp.raise_for_status()
        payload: Mapping[str, object] = resp.json()
        return GithubUser.model_validate(payload)


def fetch_repo_stats(login: GithubLogin, token: str | None = None) -> RepoStats:
    """Aggregate stars/forks/top-languages from public repos (best effort)."""
    with create_client(token) as client:
        resp = client.get(f"/users/{login}/repos", params={"per_page": "100", "sort": "updated"})
        if resp.status_code != 200:
            return RepoStats()
        raw_repos: list[object] = resp.json()
        repos: list[GithubRepo] = []
        for raw in raw_repos:
            if isinstance(raw, dict):
                repos.append(GithubRepo.model_validate(raw))
        stars = sum(r.stargazers_count for r in repos)
        forks = sum(r.forks_count for r in repos)
        langs = Counter(r.language for r in repos if r.language and not r.fork)
        top = tuple(lang for lang, _ in langs.most_common(5) if lang)
        return RepoStats(stars=stars, forks=forks, top_languages=top, repo_count=len(repos))


def fetch_avatar_bytes(avatar_url: str, token: str | None = None) -> bytes | None:
    """Download avatar bytes; returns None on any failure (image is optional)."""
    if not avatar_url:
        return None
    try:
        with create_client(token) as client:
            req_timeout = httpx.Timeout(connect=5.0, read=15.0, write=10.0, pool=10.0)
            resp = client.get(avatar_url, timeout=req_timeout)
            if resp.status_code != 200:
                return None
            return resp.content
    except (httpx.HTTPError, OSError, ValueError):
        return None
