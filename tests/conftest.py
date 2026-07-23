"""Shared test fixtures: fixture-file loader and fake HTTP/LLM clients.

No test anywhere in this suite is allowed to make a real network call —
every fake here exists to make that unnecessary.
"""
from __future__ import annotations

import json
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict:
    with (FIXTURES_DIR / name).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_fixture_text(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


class FakeResponse:
    """Stands in for a `requests.Response`."""

    def __init__(self, *, json_body: dict, status_code: int = 200):
        self._json_body = json_body
        self.status_code = status_code
        self.ok = 200 <= status_code < 300
        self.text = json.dumps(json_body)

    def json(self) -> dict:
        return self._json_body


class FakeHTTP:
    """Stands in for the `requests` module: a queue of canned responses,
    one popped per `.get()` call, in order."""

    def __init__(self, responses: list[FakeResponse]):
        self._responses = list(responses)
        self.calls: list[tuple[str, dict]] = []

    def get(self, url: str, params: dict | None = None):
        self.calls.append((url, params or {}))
        if not self._responses:
            raise AssertionError("FakeHTTP: no more canned responses")
        return self._responses.pop(0)


class FakeGeminiResponse:
    def __init__(self, text: str):
        self.text = text


class FakeGeminiModels:
    def __init__(self, response_text: str):
        self._response_text = response_text
        self.calls: list[dict] = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        return FakeGeminiResponse(self._response_text)


class FakeGeminiClient:
    """Stands in for a `google.genai.Client`."""

    def __init__(self, response_text: str):
        self.models = FakeGeminiModels(response_text)
