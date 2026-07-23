"""Tests for dsscraper.refresh_token — subprocess to `gh` is always mocked."""
import subprocess

import pytest

import dsscraper.refresh_token as module
from dsscraper.instagram import InstagramAPIError
from dsscraper.refresh_token import _persist_token


def test_persist_token_never_puts_token_in_argv(monkeypatch):
    captured = {}

    def fake_run(args, input=None, text=None, capture_output=None):
        captured["args"] = args
        captured["input"] = input
        return subprocess.CompletedProcess(args, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    _persist_token("IGAASECRETVALUE")

    assert "IGAASECRETVALUE" not in captured["args"]
    assert captured["input"] == "IGAASECRETVALUE"


def test_persist_token_raises_on_nonzero_exit(monkeypatch):
    def fake_run(args, input=None, text=None, capture_output=None):
        return subprocess.CompletedProcess(args, returncode=1, stdout="", stderr="permission denied")

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(RuntimeError):
        _persist_token("token")


def test_main_exits_nonzero_when_refresh_fails(monkeypatch):
    monkeypatch.setenv("IG_ACCESS_TOKEN", "token")
    monkeypatch.setenv("IG_USER_ID", "id")
    monkeypatch.setenv("GEMINI_API_KEY", "key")

    def fake_refresh(token, **kwargs):
        raise InstagramAPIError("expired", status_code=400, error_code=190)

    monkeypatch.setattr(module, "refresh_long_lived_token", fake_refresh)

    with pytest.raises(SystemExit) as exc_info:
        module.main()
    assert exc_info.value.code == 1
