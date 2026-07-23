"""Orchestrates fetch -> parse -> merge -> write with safe-fail on any hard error."""
from __future__ import annotations

import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from google import genai

from .config import LOOKBACK_DAYS, Config, load_config
from .events import build_event, load_events, merge_events, write_events
from .instagram import InstagramAPIError, fetch_recent_media
from .parse import parse_caption

logger = logging.getLogger(__name__)


def run(config: Config, events_path: Path, *, http=requests, llm_client=None) -> int:
    """Fetch recent media, parse captions, merge into the last-good document,
    and write atomically. On any hard failure, leave events_path untouched
    and return non-zero.
    """
    since = datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)
    try:
        media_items = fetch_recent_media(
            config.ig_access_token, config.ig_user_id, since=since, http=http
        )
    except InstagramAPIError:
        logger.exception("Instagram API fetch failed; leaving events.json untouched")
        return 1

    client = llm_client if llm_client is not None else genai.Client(api_key=config.gemini_api_key)

    incoming = []
    for media in media_items:
        caption = media.get("caption", "")
        try:
            parsed = parse_caption(caption, llm=client)
        except Exception:
            logger.exception("Skipping post %s: caption parsing failed", media.get("id"))
            continue
        if parsed is None:
            continue
        incoming.append(build_event(media, parsed))

    doc = load_events(events_path)
    doc["events"] = merge_events(doc["events"], incoming)
    doc["generated_at"] = datetime.now(timezone.utc).isoformat()

    try:
        write_events(events_path, doc)
    except Exception:
        logger.exception("Failed to write events.json; last-good file preserved")
        return 1

    return 0


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    config = load_config()
    events_path = Path(__file__).resolve().parents[2] / "events.json"
    sys.exit(run(config, events_path))


if __name__ == "__main__":
    main()
