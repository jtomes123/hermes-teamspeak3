import os
from unittest.mock import patch

import pytest

from hermes_agent_ts3.config import (
    TS3Config,
    _parse_comma_list,
    _parse_float_env,
    _parse_int_env,
)


class TestParseHelpers:
    def test_parse_comma_list_empty(self):
        assert _parse_comma_list(None) == []
        assert _parse_comma_list("") == []

    def test_parse_comma_list_single(self):
        assert _parse_comma_list("alice") == ["alice"]

    def test_parse_comma_list_multiple(self):
        assert _parse_comma_list("alice,bob,charlie") == ["alice", "bob", "charlie"]

    def test_parse_comma_list_strips_whitespace(self):
        assert _parse_comma_list(" alice , bob , charlie ") == ["alice", "bob", "charlie"]

    def test_parse_comma_list_skips_empty_items(self):
        assert _parse_comma_list("alice,,bob") == ["alice", "bob"]
        assert _parse_comma_list(",,") == []

    def test_parse_int_env_returns_default_when_none(self):
        assert _parse_int_env(None, 42) == 42

    def test_parse_int_env_parses_valid_int(self):
        assert _parse_int_env("9987", 42) == 9987
        assert _parse_int_env("0", 42) == 0
        assert _parse_int_env("-1", 42) == -1

    def test_parse_int_env_returns_default_on_invalid(self):
        assert _parse_int_env("abc", 42) == 42
        assert _parse_int_env("", 42) == 42

    def test_parse_float_env_returns_default_when_none(self):
        assert _parse_float_env(None, 3.14) == 3.14

    def test_parse_float_env_parses_valid_float(self):
        assert _parse_float_env("1.5", 3.14) == 1.5
        assert _parse_float_env("0.0", 3.14) == 0.0
        assert _parse_float_env("60", 3.14) == 60.0

    def test_parse_float_env_returns_default_on_invalid(self):
        assert _parse_float_env("abc", 3.14) == 3.14
        assert _parse_float_env("", 3.14) == 3.14


class TestTS3Config:
    def test_default_values(self):
        cfg = TS3Config()
        assert cfg.server_host == ""
        assert cfg.serverquery_port == 10011
        assert cfg.serverquery_user == ""
        assert cfg.serverquery_pass == ""
        assert cfg.voice_port == 9987
        assert cfg.home_channel == ""
        assert cfg.allowed_users == []
        assert cfg.allowed_channels == []
        assert cfg.identity_file == "ts3_identity"
        assert cfg.nickname == "Hermes"
        assert cfg.server_password == ""
        assert cfg.client_download_url == ""
        assert cfg.client_download_checksum == ""
        assert cfg.client_data_dir == "ts3_client_data"
        assert cfg.pulse_sink == "ts3_playback"
        assert cfg.pulse_source == "bot_tts"
        assert cfg.pulse_server == ""
        assert cfg.xvfb_display == ":99"
        assert cfg.reconnect_base == 1.0
        assert cfg.reconnect_max == 60.0

    def test_server_password_not_in_repr(self):
        cfg = TS3Config(server_password="secret")
        r = repr(cfg)
        assert "secret" not in r

    def test_serverquery_pass_not_in_repr(self):
        cfg = TS3Config(serverquery_pass="secret")
        r = repr(cfg)
        assert "secret" not in r

    def test_from_env_defaults(self):
        with patch.dict(os.environ, {}, clear=True):
            cfg = TS3Config.from_env()
            assert cfg.server_host == ""
            assert cfg.serverquery_port == 10011
            assert cfg.serverquery_user == ""
            assert cfg.voice_port == 9987
            assert cfg.home_channel == ""
            assert cfg.allowed_users == []
            assert cfg.allowed_channels == []
            assert cfg.identity_file == "ts3_identity"
            assert cfg.nickname == "Hermes"
            assert cfg.server_password == ""
            assert cfg.client_download_url == ""
            assert cfg.client_download_checksum == ""
            assert cfg.client_data_dir == "ts3_client_data"
            assert cfg.pulse_sink == "ts3_playback"
            assert cfg.pulse_source == "bot_tts"
            assert cfg.pulse_server == ""
            assert cfg.xvfb_display == ":99"
            assert cfg.reconnect_base == 1.0
            assert cfg.reconnect_max == 60.0

    def test_from_env_all_fields_set(self):
        env = {
            "TS3_SERVER_HOST": "ts.example.com",
            "TS3_SERVERQUERY_PORT": "10022",
            "TS3_SERVERQUERY_USER": "admin",
            "TS3_SERVERQUERY_PASS": "adminpass",
            "TS3_VOICE_PORT": "9999",
            "TS3_HOME_CHANNEL": "Home",
            "TS3_ALLOWED_USERS": "alice,bob,charlie",
            "TS3_ALLOWED_CHANNELS": "General,Support",
            "TS3_IDENTITY_FILE": "my_identity",
            "TS3_NICKNAME": "MyBot",
            "TS3_SERVER_PASSWORD": "ts3pass",
            "TS3_CLIENT_DOWNLOAD_URL": "https://example.com/ts3.tar.gz",
            "TS3_CLIENT_DOWNLOAD_CHECKSUM": "abc123",
            "TS3_CLIENT_DATA_DIR": "/opt/ts3_data",
            "TS3_PULSE_SINK": "custom_sink",
            "TS3_PULSE_SOURCE": "custom_source",
            "TS3_PULSE_SERVER": "unix:/tmp/pulse",
            "TS3_XVFB_DISPLAY": ":100",
            "TS3_RECONNECT_BASE": "2.0",
            "TS3_RECONNECT_MAX": "120.0",
        }
        with patch.dict(os.environ, env, clear=True):
            cfg = TS3Config.from_env()
            assert cfg.server_host == "ts.example.com"
            assert cfg.serverquery_port == 10022
            assert cfg.serverquery_user == "admin"
            assert cfg.serverquery_pass == "adminpass"
            assert cfg.voice_port == 9999
            assert cfg.home_channel == "Home"
            assert cfg.allowed_users == ["alice", "bob", "charlie"]
            assert cfg.allowed_channels == ["General", "Support"]
            assert cfg.identity_file == "my_identity"
            assert cfg.nickname == "MyBot"
            assert cfg.server_password == "ts3pass"
            assert cfg.client_download_url == "https://example.com/ts3.tar.gz"
            assert cfg.client_download_checksum == "abc123"
            assert cfg.client_data_dir == "/opt/ts3_data"
            assert cfg.pulse_sink == "custom_sink"
            assert cfg.pulse_source == "custom_source"
            assert cfg.pulse_server == "unix:/tmp/pulse"
            assert cfg.xvfb_display == ":100"
            assert cfg.reconnect_base == 2.0
            assert cfg.reconnect_max == 120.0

    def test_from_env_invalid_ports_fallback_to_defaults(self):
        env = {
            "TS3_SERVERQUERY_PORT": "not_a_number",
            "TS3_VOICE_PORT": "xyz",
            "TS3_RECONNECT_BASE": "abc",
            "TS3_RECONNECT_MAX": "def",
        }
        with patch.dict(os.environ, env, clear=True):
            cfg = TS3Config.from_env()
            assert cfg.serverquery_port == 10011
            assert cfg.voice_port == 9987
            assert cfg.reconnect_base == 1.0
            assert cfg.reconnect_max == 60.0

    def test_from_env_allowed_users_empty_string(self):
        with patch.dict(os.environ, {"TS3_ALLOWED_USERS": ""}, clear=True):
            cfg = TS3Config.from_env()
            assert cfg.allowed_users == []

    def test_from_env_allowed_channels_empty(self):
        with patch.dict(os.environ, {"TS3_ALLOWED_CHANNELS": ","}, clear=True):
            cfg = TS3Config.from_env()
            assert cfg.allowed_channels == []
