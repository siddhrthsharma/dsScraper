"""HTTP client for graph.instagram.com — media fetch and token refresh.

Nothing outside this module talks to Meta directly.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from datetime import datetime

import requests
from dateutil import parser as date_parser

from .config import API_VERSION, GRAPH_HOST, MEDIA_FIELDS

_RETRYABLE_STATUS = {429, 500, 502, 503, 504}
_MAX_ATTEMPTS = 3
_TOKEN_PARAM_RE = re.compile(r"(access_token=)[^&\s]+")


class InstagramAPIError(Exception):
    """Raised when graph.instagram.com returns a non-2xx response, or all
    retries of a transient error are exhausted."""

    def __init__(self, message: str, *, status_code: int, error_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code


@dataclass
class RefreshResult:
    access_token: str
    expires_in: int


def _error_from_response(response) -> InstagramAPIError:
    body = {}
    try:
        body = response.json()
    except ValueError:
        pass
    error = body.get("error", {})
    return InstagramAPIError(
        error.get("message", getattr(response, "text", "")),
        status_code=response.status_code,
        error_code=error.get("code"),
    )


def _get_with_retries(http, url, params, *, sleep):
    last_error: InstagramAPIError | None = None
    for attempt in range(_MAX_ATTEMPTS):
        try:
            response = http.get(url, params=params)
        except requests.exceptions.RequestException as exc:
            last_error = InstagramAPIError(
                _TOKEN_PARAM_RE.sub(r"\1<redacted>", str(exc)), status_code=0
            )
            if attempt < _MAX_ATTEMPTS - 1:
                sleep(2**attempt)
            continue
        if response.status_code in _RETRYABLE_STATUS:
            last_error = _error_from_response(response)
            if attempt < _MAX_ATTEMPTS - 1:
                sleep(2**attempt)
            continue
        if not response.ok:
            raise _error_from_response(response)
        return response
    raise last_error


def fetch_recent_media(
    access_token: str,
    ig_user_id: str,
    *,
    since: datetime,
    limit: int = 50,
    http=requests,
    sleep=time.sleep,
) -> list[dict]:
    """Fetch media newer than `since`, newest first, following pagination.

    `since`/`until` are not reliably supported on this endpoint (they're
    insights-only), so we filter client-side and stop paginating as soon
    as a page yields an item older than `since`.
    """
    url = f"{GRAPH_HOST}/{API_VERSION}/{ig_user_id}/media"
    params = {
        "fields": ",".join(MEDIA_FIELDS),
        "limit": limit,
        "access_token": access_token,
    }
    results: list[dict] = []
    while url:
        response = _get_with_retries(http, url, params, sleep=sleep)
        body = response.json()
        for item in body.get("data", []):
            timestamp = date_parser.parse(item["timestamp"])
            if timestamp < since:
                return results
            results.append(item)
        url = body.get("paging", {}).get("next")
        params = {}  # `next` is already a full URL carrying its own params
    return results


def refresh_long_lived_token(access_token: str, *, http=requests, sleep=time.sleep) -> RefreshResult:
    """Exchange a >=24h-old long-lived token for a new one, TTL reset to
    ~60 days. No app id/secret involved — Instagram Login refresh needs
    only the current token."""
    url = f"{GRAPH_HOST}/refresh_access_token"
    params = {"grant_type": "ig_refresh_token", "access_token": access_token}
    response = _get_with_retries(http, url, params, sleep=sleep)
    body = response.json()
    return RefreshResult(access_token=body["access_token"], expires_in=body["expires_in"])
