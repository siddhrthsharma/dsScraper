"""Caption -> structured event: deterministic marker parser + Gemini fallback."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime

from dateutil import parser as date_parser

MARKER = "#dsevent"

_LABEL_ALIASES = {
    "event": "title",
    "title": "title",
    "when": "when",
    "date": "when",
    "time": "when",
    "where": "location",
    "location": "location",
    "repeats": "recurrence",
    "recurring": "recurrence",
}

_LINE_RE = re.compile(r"^\s*([A-Za-z]+)\s*:\s*(.+?)\s*$")


@dataclass
class ParsedEvent:
    title: str
    start: datetime | None
    end: datetime | None
    location: str | None
    description: str | None
    recurrence: str | None
    parsed_by: str
    confidence: float


def _split_when(raw: str) -> tuple[datetime | None, datetime | None]:
    """Parse a `When` value: a single moment, or a `start - end` range."""
    parts = re.split(r"\s*[-–—]\s*", raw, maxsplit=1)
    try:
        start = date_parser.parse(parts[0], fuzzy=True)
    except (ValueError, OverflowError):
        return None, None
    if len(parts) == 1:
        return start, None
    try:
        end = date_parser.parse(parts[1], fuzzy=True, default=start)
    except (ValueError, OverflowError):
        return start, None
    return start, end


def parse_marker(caption: str) -> ParsedEvent | None:
    """Parse labeled lines following MARKER. Requires at least a title.

    A missing/unparseable `When` yields start=None (undated) rather than
    dropping the event — silently losing an event is worse than "Date TBA".
    """
    if MARKER not in caption.lower():
        return None

    fields: dict[str, str] = {}
    for line in caption.splitlines():
        match = _LINE_RE.match(line)
        if not match:
            continue
        key = _LABEL_ALIASES.get(match.group(1).strip().lower())
        if key:
            fields[key] = match.group(2).strip()

    title = fields.get("title")
    if not title:
        return None

    start, end = (None, None)
    if "when" in fields:
        start, end = _split_when(fields["when"])

    return ParsedEvent(
        title=title,
        start=start,
        end=end,
        location=fields.get("location"),
        description=None,
        recurrence=fields.get("recurrence"),
        parsed_by="marker",
        confidence=1.0,
    )


_GEMINI_SCHEMA = {
    "type": "object",
    "properties": {
        "is_event": {"type": "boolean"},
        "title": {"type": "string"},
        "start": {"type": "string"},
        "end": {"type": "string"},
        "location": {"type": "string"},
        "description": {"type": "string"},
        "recurrence": {"type": "string"},
        "confidence": {"type": "number"},
    },
    "required": ["is_event"],
}

_GEMINI_PROMPT = (
    "Extract event details from this Instagram caption for a university club. "
    "Set is_event=false if the caption does not announce a specific event. "
    "start/end must be ISO 8601 datetimes when a date is stated, otherwise omit them. "
    "Caption:\n{caption}"
)


def gemini_extract(caption: str, *, client) -> ParsedEvent | None:
    """Call Gemini with structured-output JSON mode; return None for non-events
    or when the model can't produce a usable title."""
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=_GEMINI_PROMPT.format(caption=caption),
        config={
            "response_mime_type": "application/json",
            "response_schema": _GEMINI_SCHEMA,
        },
    )
    data = json.loads(response.text)

    if not data.get("is_event") or not data.get("title"):
        return None

    def _parse_dt(value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            return date_parser.parse(value)
        except (ValueError, OverflowError):
            return None

    return ParsedEvent(
        title=data["title"],
        start=_parse_dt(data.get("start")),
        end=_parse_dt(data.get("end")),
        location=data.get("location") or None,
        description=data.get("description") or None,
        recurrence=data.get("recurrence") or None,
        parsed_by="llm",
        confidence=float(data.get("confidence", 0.7)),
    )


def parse_caption(caption: str, *, llm=None) -> ParsedEvent | None:
    """Marker path first; Gemini fallback ONLY when the marker is absent
    entirely. A marker present but malformed does not fall through to the
    LLM — it's treated as "not a parseable event", not "try harder"."""
    marker_result = parse_marker(caption)
    if marker_result is not None:
        return marker_result
    if MARKER in caption.lower():
        return None
    if llm is None:
        return None
    return gemini_extract(caption, client=llm)
