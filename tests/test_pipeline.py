"""End-to-end pipeline tests. No network: FakeHTTP + FakeGeminiClient only."""
import json

from conftest import FakeGeminiClient, FakeHTTP, FakeResponse, load_fixture, load_fixture_text

from dsscraper.config import Config
from dsscraper.instagram import InstagramAPIError
from dsscraper.pipeline import run


def _config() -> Config:
    return Config(ig_access_token="token", ig_user_id="17841400000000000", gemini_api_key="key")


def _no_next(page: dict) -> dict:
    return {**page, "paging": {"cursors": page["paging"]["cursors"]}}


def test_run_writes_marker_events_end_to_end(tmp_path):
    page = _no_next(load_fixture("media_response_page1.json"))
    http = FakeHTTP([FakeResponse(json_body=page)])
    events_path = tmp_path / "events.json"

    exit_code = run(_config(), events_path, http=http, llm_client=FakeGeminiClient("{}"))

    assert exit_code == 0
    doc = json.loads(events_path.read_text())
    assert len(doc["events"]) == 1  # only the #dsevent-tagged post; the other has no marker and Gemini says "{}"
    assert doc["events"][0]["title"] == "Intro to Pandas Workshop"


def test_run_uses_llm_for_non_marker_captions(tmp_path):
    page = {
        "data": [{
            "id": "1",
            "caption": "No tag, but a real event is happening!",
            "permalink": "https://instagram.com/p/1/",
            "media_url": "https://img/1.jpg",
            "timestamp": "2026-09-20T18:00:00+0000",
        }],
        "paging": {"cursors": {"before": "b", "after": "a"}},
    }
    http = FakeHTTP([FakeResponse(json_body=page)])
    llm = FakeGeminiClient(load_fixture_text("gemini_response_event.json"))
    events_path = tmp_path / "events.json"

    exit_code = run(_config(), events_path, http=http, llm_client=llm)

    assert exit_code == 0
    doc = json.loads(events_path.read_text())
    assert doc["events"][0]["parsed_by"] == "llm"


def test_run_leaves_last_good_file_untouched_on_api_error(tmp_path):
    events_path = tmp_path / "events.json"
    good_doc = {"schema_version": 1, "generated_at": "2026-07-01T00:00:00+00:00", "events": []}
    events_path.write_text(json.dumps(good_doc))

    class FailingHTTP:
        def get(self, url, params=None):
            raise InstagramAPIError("boom", status_code=400, error_code=190)

    exit_code = run(_config(), events_path, http=FailingHTTP(), llm_client=FakeGeminiClient("{}"))

    assert exit_code == 1
    assert json.loads(events_path.read_text()) == good_doc


def test_run_is_idempotent_on_second_identical_run(tmp_path):
    page = _no_next(load_fixture("media_response_page1.json"))
    events_path = tmp_path / "events.json"

    run(_config(), events_path, http=FakeHTTP([FakeResponse(json_body=page)]), llm_client=FakeGeminiClient("{}"))
    first_ids = [e["id"] for e in json.loads(events_path.read_text())["events"]]

    run(_config(), events_path, http=FakeHTTP([FakeResponse(json_body=page)]), llm_client=FakeGeminiClient("{}"))
    second_ids = [e["id"] for e in json.loads(events_path.read_text())["events"]]

    assert first_ids == second_ids


def test_run_skips_post_with_no_parseable_event(tmp_path):
    page = {
        "data": [{
            "id": "1",
            "caption": "Just vibing, nothing structured here",
            "permalink": "https://instagram.com/p/1/",
            "media_url": "https://img/1.jpg",
            "timestamp": "2026-09-20T18:00:00+0000",
        }],
        "paging": {"cursors": {"before": "b", "after": "a"}},
    }
    http = FakeHTTP([FakeResponse(json_body=page)])
    llm = FakeGeminiClient(load_fixture_text("gemini_response_not_event.json"))
    events_path = tmp_path / "events.json"

    exit_code = run(_config(), events_path, http=http, llm_client=llm)

    assert exit_code == 0
    assert json.loads(events_path.read_text())["events"] == []
