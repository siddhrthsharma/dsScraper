"""Tests for dsscraper.instagram — no network calls, FakeHTTP only."""
from datetime import datetime, timezone

import pytest
import requests
from conftest import FakeHTTP, FakeResponse, load_fixture

from dsscraper.instagram import InstagramAPIError, fetch_recent_media, refresh_long_lived_token


def _no_next(page: dict) -> dict:
    return {**page, "paging": {"cursors": page["paging"]["cursors"]}}


def test_fetch_recent_media_follows_pagination_and_stops_at_since():
    page1 = load_fixture("media_response_page1.json")
    page2 = load_fixture("media_response_page2.json")
    http = FakeHTTP([FakeResponse(json_body=page1), FakeResponse(json_body=page2)])

    since = datetime(2026, 8, 1, tzinfo=timezone.utc)
    results = fetch_recent_media("token", "17841400000000000", since=since, http=http)

    assert [item["id"] for item in results] == ["17895694728", "17895694729", "17895694730"]
    assert len(http.calls) == 2


def test_fetch_recent_media_single_page_no_pagination():
    page = _no_next(load_fixture("media_response_page1.json"))
    http = FakeHTTP([FakeResponse(json_body=page)])
    since = datetime(2020, 1, 1, tzinfo=timezone.utc)
    results = fetch_recent_media("token", "17841400000000000", since=since, http=http)
    assert len(results) == 2
    assert len(http.calls) == 1


def test_fetch_recent_media_raises_on_oauth_error():
    error_body = load_fixture("error_response_oauth.json")
    http = FakeHTTP([FakeResponse(json_body=error_body, status_code=400)])
    since = datetime(2020, 1, 1, tzinfo=timezone.utc)
    with pytest.raises(InstagramAPIError) as exc_info:
        fetch_recent_media("token", "17841400000000000", since=since, http=http)
    assert exc_info.value.error_code == 190


def test_fetch_recent_media_retries_transient_errors_then_succeeds():
    page = _no_next(load_fixture("media_response_page1.json"))
    http = FakeHTTP([
        FakeResponse(json_body={"error": {"message": "rate limited"}}, status_code=429),
        FakeResponse(json_body=page),
    ])
    since = datetime(2020, 1, 1, tzinfo=timezone.utc)
    results = fetch_recent_media("token", "id", since=since, http=http, sleep=lambda _: None)
    assert len(results) == 2
    assert len(http.calls) == 2


def test_fetch_recent_media_raises_after_max_retries():
    http = FakeHTTP([
        FakeResponse(json_body={"error": {"message": "rate limited"}}, status_code=429),
        FakeResponse(json_body={"error": {"message": "rate limited"}}, status_code=429),
        FakeResponse(json_body={"error": {"message": "rate limited"}}, status_code=429),
    ])
    since = datetime(2020, 1, 1, tzinfo=timezone.utc)
    with pytest.raises(InstagramAPIError):
        fetch_recent_media("token", "id", since=since, http=http, sleep=lambda _: None)


def test_fetch_recent_media_retries_network_errors():
    calls = {"n": 0}
    page = _no_next(load_fixture("media_response_page1.json"))

    class FlakyHTTP:
        def get(self, url, params=None):
            calls["n"] += 1
            if calls["n"] < 2:
                raise requests.exceptions.ConnectionError("boom")
            return FakeResponse(json_body=page)

    since = datetime(2020, 1, 1, tzinfo=timezone.utc)
    results = fetch_recent_media("token", "id", since=since, http=FlakyHTTP(), sleep=lambda _: None)
    assert len(results) == 2


def test_refresh_long_lived_token_returns_new_token_and_ttl():
    body = load_fixture("refresh_token_response.json")
    http = FakeHTTP([FakeResponse(json_body=body)])
    result = refresh_long_lived_token("old-token", http=http)
    assert result.access_token == body["access_token"]
    assert result.expires_in == body["expires_in"]
    _, params = http.calls[0]
    assert params["grant_type"] == "ig_refresh_token"
    assert params["access_token"] == "old-token"


def test_refresh_long_lived_token_raises_on_error():
    error_body = load_fixture("error_response_oauth.json")
    http = FakeHTTP([FakeResponse(json_body=error_body, status_code=400)])
    with pytest.raises(InstagramAPIError):
        refresh_long_lived_token("old-token", http=http)
