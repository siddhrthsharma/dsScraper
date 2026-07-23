"""events.json schema, dedupe/merge, and atomic I/O."""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from .parse import ParsedEvent

SCHEMA_VERSION = 1


class EventsValidationError(Exception):
    """Raised when a document doesn't match the events.json schema."""


def _normalize_key(title: str, start: datetime | None) -> tuple[str, str]:
    normalized_title = " ".join(title.lower().split())
    date_key = start.date().isoformat() if start else "undated"
    return normalized_title, date_key


def build_event(media: dict, parsed: ParsedEvent) -> dict:
    """Combine an Instagram media item with its parsed caption into an event record."""
    now = datetime.now(timezone.utc).isoformat()
    if parsed.recurrence:
        date_status = "recurring"
    elif parsed.start:
        date_status = "confirmed"
    else:
        date_status = "undated"
    return {
        "id": f"ig_{media['id']}",
        "title": parsed.title,
        "start": parsed.start.isoformat() if parsed.start else None,
        "end": parsed.end.isoformat() if parsed.end else None,
        "all_day": False,
        "date_status": date_status,
        "recurrence": parsed.recurrence,
        "location": parsed.location,
        "description": parsed.description,
        "permalink": media.get("permalink"),
        "image_url": media.get("media_url") or media.get("thumbnail_url"),
        "source_post_ids": [media["id"]],
        "parsed_by": parsed.parsed_by,
        "confidence": parsed.confidence,
        "updated_at": now,
    }


def _parse_start(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def merge_events(existing: list[dict], incoming: list[dict]) -> list[dict]:
    """Dedupe by IG post id; collapse same (normalized title, date) across
    posts, keeping the higher-confidence record's fields and unioning
    source_post_ids."""
    by_id: dict[str, dict] = {event["id"]: dict(event) for event in existing}
    for event in incoming:
        by_id[event["id"]] = dict(event)

    grouped: dict[tuple[str, str], dict] = {}
    for event in by_id.values():
        key = _normalize_key(event["title"], _parse_start(event.get("start")))
        best = grouped.get(key)
        if best is None:
            grouped[key] = dict(event)
            continue
        winner = event if event["confidence"] > best["confidence"] else best
        merged = dict(winner)
        merged["source_post_ids"] = sorted(set(best["source_post_ids"]) | set(event["source_post_ids"]))
        grouped[key] = merged

    return sorted(grouped.values(), key=lambda e: e["id"])


def validate(doc: dict) -> None:
    """Raise EventsValidationError if `doc` doesn't match the schema."""
    if doc.get("schema_version") != SCHEMA_VERSION:
        raise EventsValidationError(f"unsupported schema_version: {doc.get('schema_version')!r}")
    if "events" not in doc or not isinstance(doc["events"], list):
        raise EventsValidationError("missing or invalid 'events' list")
    for event in doc["events"]:
        for field in ("id", "title", "date_status", "source_post_ids", "parsed_by", "confidence"):
            if field not in event:
                raise EventsValidationError(f"event {event.get('id', '?')} missing field {field!r}")


def load_events(path: Path) -> dict:
    """Return the last-good document, or a seed document if the file is absent."""
    if not path.exists():
        return {"schema_version": SCHEMA_VERSION, "generated_at": None, "events": []}
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_events(path: Path, doc: dict) -> None:
    """Validate, then write atomically via temp file + os.replace so a
    crash mid-write can never leave a partial/corrupt events.json."""
    validate(doc)
    fd, tmp_path = tempfile.mkstemp(dir=path.parent, prefix=".events-", suffix=".json.tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(doc, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(tmp_path, path)
    except BaseException:
        os.unlink(tmp_path)
        raise
