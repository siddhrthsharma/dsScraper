"""Tests for dsscraper.config."""
import pytest

from dsscraper.config import ConfigError, load_config


def test_load_config_reads_all_required_vars():
    env = {"IG_ACCESS_TOKEN": "t", "IG_USER_ID": "u", "GEMINI_API_KEY": "g"}
    config = load_config(env)
    assert config.ig_access_token == "t"
    assert config.ig_user_id == "u"
    assert config.gemini_api_key == "g"


def test_load_config_raises_listing_all_missing_vars():
    with pytest.raises(ConfigError) as exc_info:
        load_config({"IG_ACCESS_TOKEN": "t"})
    message = str(exc_info.value)
    assert "IG_USER_ID" in message
    assert "GEMINI_API_KEY" in message


def test_load_config_treats_empty_string_as_missing():
    env = {"IG_ACCESS_TOKEN": "", "IG_USER_ID": "u", "GEMINI_API_KEY": "g"}
    with pytest.raises(ConfigError):
        load_config(env)
