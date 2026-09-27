"""Typed GitHub API models. Boundary: raw JSON -> parsed Pydantic."""

from __future__ import annotations

from datetime import datetime
from typing import NewType

from pydantic import BaseModel, ConfigDict, Field

GithubLogin = NewType("GithubLogin", str)


class GithubUser(BaseModel):
    """Parsed GitHub user profile from GET /users/{login}."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    login: str
    name: str | None = None
    bio: str | None = None
    company: str | None = None
    location: str | None = None
    blog: str | None = None
    twitter_username: str | None = None
    public_repos: int = 0
    public_gists: int = 0
    followers: int = 0
    following: int = 0
    created_at: datetime | None = None
    avatar_url: str = Field(default="")


class RepoStats(BaseModel):
    """Aggregated stats computed from a user's public repos."""

    model_config = ConfigDict(frozen=True)

    stars: int = 0
    forks: int = 0
    top_languages: tuple[str, ...] = ()
    repo_count: int = 0


class GithubRepo(BaseModel):
    """Subset of GET /users/{login}/repos used for aggregation."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    stargazers_count: int = 0
    forks_count: int = 0
    language: str | None = None
    fork: bool = False


def normalize_login(raw: str) -> GithubLogin:
    """Parse a CLI username into a branded login."""
    cleaned = raw.strip().lstrip("@")
    return GithubLogin(cleaned.lower())
