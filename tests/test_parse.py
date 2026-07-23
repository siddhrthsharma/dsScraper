"""Tests for dsscraper.parse — no network calls."""
from datetime import datetime

from conftest import FakeGeminiClient, load_fixture_text

from dsscraper.parse import gemini_extract, parse_caption, parse_marker


def test_parse_marker_extracts_title_and_range():
    caption = (
        "Join us! #dsevent\n"
        "Event: Intro to Pandas Workshop\n"
        "When: Oct 5, 2026 6:00pm - 7:30pm\n"
        "Where: Phelps 1260"
    )
    result = parse_marker(caption)
    assert result.title == "Intro to Pandas Workshop"
    assert result.location == "Phelps 1260"
    assert result.start == datetime(2026, 10, 5, 18, 0)
    assert result.end == datetime(2026, 10, 5, 19, 30)
    assert result.parsed_by == "marker"
    assert result.confidence == 1.0


def test_parse_marker_missing_when_is_undated_not_dropped():
    caption = "#dsevent\nEvent: Mystery Meeting"
    result = parse_marker(caption)
    assert result.title == "Mystery Meeting"
    assert result.start is None


def test_parse_marker_missing_title_returns_none():
    caption = "#dsevent\nWhen: Oct 5, 2026"
    assert parse_marker(caption) is None


def test_parse_marker_no_marker_returns_none():
    assert parse_marker("Just a regular caption with no tag") is None


def test_parse_marker_is_case_insensitive_and_label_tolerant():
    caption = "#DSEvent\ntitle: Board Game Night\ndate: Nov 1, 2026 7pm\nlocation: Girvetz 1004"
    result = parse_marker(caption)
    assert result.title == "Board Game Night"
    assert result.location == "Girvetz 1004"


def test_parse_marker_combines_separate_date_and_time_lines():
    caption = (
        "#dsevent\n"
        "Event: Some Meeting\n"
        "Date: Oct 5, 2026\n"
        "Time: 6:00pm"
    )
    result = parse_marker(caption)
    assert result.start == datetime(2026, 10, 5, 18, 0)


def test_gemini_extract_returns_event_from_structured_response():
    client = FakeGeminiClient(load_fixture_text("gemini_response_event.json"))
    caption = "Come hang out with us this Monday for snacks and networking!"
    result = gemini_extract(caption, client=client)
    assert result.title == "Fall Kickoff Mixer"
    assert result.parsed_by == "llm"
    assert result.confidence == 0.85
    assert client.models.calls[0]["config"]["response_mime_type"] == "application/json"


def test_gemini_extract_returns_none_for_non_event():
    client = FakeGeminiClient(load_fixture_text("gemini_response_not_event.json"))
    assert gemini_extract("just chilling, no event here", client=client) is None


def test_gemini_extract_defaults_confidence_when_explicitly_null():
    client = FakeGeminiClient(
        '{"is_event": true, "title": "Test Event", "confidence": null}'
    )
    result = gemini_extract("some caption", client=client)
    assert result.title == "Test Event"
    assert result.confidence == 0.7


def test_parse_caption_prefers_marker_over_llm():
    caption = "#dsevent\nEvent: Marker Wins\nWhen: Dec 1, 2026 5pm"
    client = FakeGeminiClient(load_fixture_text("gemini_response_not_event.json"))
    result = parse_caption(caption, llm=client)
    assert result.parsed_by == "marker"
    assert client.models.calls == []


def test_parse_caption_falls_back_to_llm_when_no_marker():
    client = FakeGeminiClient(load_fixture_text("gemini_response_event.json"))
    result = parse_caption("no tag here, but a real event happened", llm=client)
    assert result.parsed_by == "llm"


def test_parse_caption_marker_present_but_malformed_skips_llm_fallback():
    caption = "#dsevent\nWhen: Dec 1, 2026 5pm"  # no title -> parse_marker returns None
    client = FakeGeminiClient(load_fixture_text("gemini_response_event.json"))
    result = parse_caption(caption, llm=client)
    assert result is None
    assert client.models.calls == []
