"""Refresh the long-lived Instagram token and persist it to the GitHub secret.

Runs as a separate workflow step, AFTER the data pipeline has already
written events.json, so a refresh failure never blocks the daily data pull.
The token is passed to `gh` on stdin — never as a CLI argument, and never
logged — so it can't leak into process listings or Action logs.
"""
from __future__ import annotations

import logging
import subprocess
import sys

from .config import load_config
from .instagram import InstagramAPIError, refresh_long_lived_token

logger = logging.getLogger(__name__)


def _persist_token(new_token: str) -> None:
    result = subprocess.run(
        ["gh", "secret", "set", "IG_ACCESS_TOKEN"],
        input=new_token,
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        raise RuntimeError("gh secret set failed (see job logs for gh's stderr)")


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    config = load_config()
    try:
        result = refresh_long_lived_token(config.ig_access_token)
    except InstagramAPIError:
        logger.exception("Token refresh failed; keeping existing IG_ACCESS_TOKEN")
        sys.exit(1)

    try:
        _persist_token(result.access_token)
    except RuntimeError:
        logger.exception("Failed to persist refreshed token to GitHub secret")
        sys.exit(1)

    logger.info("IG_ACCESS_TOKEN refreshed, new TTL %s seconds", result.expires_in)


if __name__ == "__main__":
    main()
