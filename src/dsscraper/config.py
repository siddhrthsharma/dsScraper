"""Environment configuration and Instagram Graph API constants."""
from __future__ import annotations

import os
from dataclasses import dataclass

API_VERSION = "v25.0"
GRAPH_HOST = "https://graph.instagram.com"
LOOKBACK_DAYS = 90
MEDIA_FIELDS = [
    "id",
    "caption",
    "media_type",
    "media_url",
    "thumbnail_url",
    "permalink",
    "timestamp",
    "children{media_url,media_type}",
]

REQUIRED_ENV_VARS = ("IG_ACCESS_TOKEN", "IG_USER_ID", "GEMINI_API_KEY")


class ConfigError(Exception):
    """Raised when required environment variables are missing."""


@dataclass(frozen=True)
class Config:
    ig_access_token: str
    ig_user_id: str
    gemini_api_key: str


def load_config(env: dict | None = None) -> Config:
    """Read required env vars from `env` (defaults to `os.environ`).

    Raises ConfigError listing every missing variable at once, so a
    misconfigured Action fails with one readable message instead of one
    KeyError per variable.
    """
    source = env if env is not None else os.environ
    missing = [name for name in REQUIRED_ENV_VARS if not source.get(name)]
    if missing:
        raise ConfigError(f"missing required environment variables: {', '.join(missing)}")
    return Config(
        ig_access_token=source["IG_ACCESS_TOKEN"],
        ig_user_id=source["IG_USER_ID"],
        gemini_api_key=source["GEMINI_API_KEY"],
    )
