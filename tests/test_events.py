"""Tests for dsscraper.events — schema, merge, atomic I/O."""
from datetime import datetime, timezone

import pytest

from dsscraper.events import (
    SCHEMA_VERSION,
    EventsValidationError,
    build_event,
    load_events,
    merge_events,
    validate,
    write_events,
)
from dsscraper.parse import ParsedEvent


def _media(id_="1", permalink="https://instagram.com/p/x/", media_url="https://img/x.jpg"):
    return {"id": id_, "permalink": permalink, "media_url": media_url}


def _parsed(title="Workshop", start=None, confidence=1.0, parsed_by="marker", recurrence=None):
    return ParsedEvent(
        title=title, start=start, end=None, location="Room 1", description=None,
        recurrence=recurrence, parsed_by=parsed_by, confidence=confidence,
    )


def test_build_event_confirmed_date_status():
    event = build_event(_media(), _parsed(start=datetime(2026, 10, 5, 18, 0, tzinfo=timezone.utc)))
    assert event["id"] == "ig_1"
    assert event["date_status"] == "confirmed"
    assert event["source_post_ids"] == ["1"]


def test_build_event_undated_when_no_start():
    event = build_event(_media(), _parsed(start=None))
    assert event["date_status"] == "undated"
    assert event["start"] is None


def test_build_event_recurring_when_recurrence_set():
    event = build_event(_media(), _parsed(start=None, recurrence="Every Tuesday"))
    assert event["date_status"] == "recurring"


def test_merge_events_dedupes_by_id():
    existing = [build_event(_media("1"), _parsed())]
    incoming = [build_event(_media("1"), _parsed(title="Updated Title"))]
    merged = merge_events(existing, incoming)
    assert len(merged) == 1
    assert merged[0]["title"] == "Updated Title"


def test_merge_events_collapses_same_title_and_date_across_posts():
    start = datetime(2026, 10, 5, 18, 0, tzinfo=timezone.utc)
    existing = [build_event(_media("1"), _parsed(title="Pandas Workshop", start=start, confidence=1.0))]
    incoming = [build_event(_media("2"), _parsed(title="pandas workshop", start=start, confidence=0.8))]
    merged = merge_events(existing, incoming)
    assert len(merged) == 1
    assert sorted(merged[0]["source_post_ids"]) == ["1", "2"]
    assert merged[0]["confidence"] == 1.0  # kept the higher-confidence record


def test_merge_events_keeps_distinct_undated_events_separate():
    existing = [build_event(_media("1"), _parsed(title="Meeting A", start=None))]
    incoming = [build_event(_media("2"), _parsed(title="Meeting B", start=None))]
    merged = merge_events(existing, incoming)
    assert len(merged) == 2


def test_validate_rejects_wrong_schema_version():
    with pytest.raises(EventsValidationError):
        validate({"schema_version": 999, "events": []})


def test_validate_rejects_missing_events_key():
    with pytest.raises(EventsValidationError):
        validate({"schema_version": SCHEMA_VERSION})


def test_load_events_returns_seed_when_file_missing(tmp_path):
    doc = load_events(tmp_path / "missing.json")
    assert doc == {"schema_version": SCHEMA_VERSION, "generated_at": None, "events": []}


def test_write_events_then_load_events_roundtrip(tmp_path):
    path = tmp_path / "events.json"
    doc = {"schema_version": SCHEMA_VERSION, "generated_at": "2026-07-22T00:00:00+00:00", "events": []}
    write_events(path, doc)
    assert load_events(path) == doc


def test_write_events_is_atomic_leaves_no_temp_file_on_success(tmp_path):
    path = tmp_path / "events.json"
    write_events(path, {"schema_version": SCHEMA_VERSION, "generated_at": None, "events": []})
    assert list(tmp_path.glob(".events-*")) == []


def test_write_events_rejects_invalid_doc_and_leaves_existing_file_untouched(tmp_path):
    path = tmp_path / "events.json"
    good_doc = {"schema_version": SCHEMA_VERSION, "generated_at": None, "events": []}
    write_events(path, good_doc)
    with pytest.raises(EventsValidationError):
        write_events(path, {"schema_version": 999, "events": []})
    assert load_events(path) == good_doc


def test_write_events_cleans_up_temp_file_on_mid_write_failure(tmp_path, monkeypatch):
    """Verify cleanup when json.dump (post-temp-file creation) fails.

    This exercises the except BaseException: os.unlink(tmp_path) branch
    that ensures atomicity even if something fails *after* mkstemp.
    """
    path = tmp_path / "events.json"
    good_doc = {"schema_version": SCHEMA_VERSION, "generated_at": None, "events": []}

    # Write an initial good file and save its content to verify later.
    write_events(path, good_doc)
    original_content = path.read_bytes()

    # Monkeypatch json.dump to raise an exception after temp file exists.
    def failing_dump(*args, **kwargs):
        raise RuntimeError("Simulated json.dump failure")

    monkeypatch.setattr("dsscraper.events.json.dump", failing_dump)

    # Call write_events with a valid doc (passes validation, creates temp file, then fails on dump).
    new_doc = {"schema_version": SCHEMA_VERSION, "generated_at": "2026-07-22T12:00:00+00:00", "events": []}
    with pytest.raises(RuntimeError, match="Simulated json.dump failure"):
        write_events(path, new_doc)

    # Assert no temp files remain.
    assert list(tmp_path.glob(".events-*")) == [], "Temp file was not cleaned up"

    # Assert the original file is byte-for-byte unchanged.
    assert path.read_bytes() == original_content, "Original file was modified"
