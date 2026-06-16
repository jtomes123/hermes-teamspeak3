from unittest.mock import MagicMock, patch

import pytest

from hermes_agent_ts3.commands import (
    COMMANDS_HELP,
    VOICE_HELP,
    CommandContext,
    CommandHandler,
    CommandResult,
)
from hermes_agent_ts3.config import TS3Config


def _make_config(**kwargs) -> TS3Config:
    cfg = TS3Config()
    for k, v in kwargs.items():
        object.__setattr__(cfg, k, v)
    return cfg


def _make_ctx(**kwargs) -> CommandContext:
    defaults = {
        "invoker_name": "TestUser",
        "invoker_id": 1,
        "invoker_uid": "uid-1",
        "invoker_channel_id": 42,
        "invoker_channel_name": "General",
        "current_channel_id": 7,
        "current_channel_name": "Home",
        "home_channel_id": 7,
        "voice_mode": "on",
        "uptime_seconds": 3600.0,
        "chat_id": "1",
    }
    defaults.update(kwargs)
    return CommandContext(**defaults)


class TestParseCommand:
    @pytest.fixture
    def handler(self):
        return CommandHandler(_make_config(command_prefix="!"))

    def test_parses_simple_command(self, handler):
        assert handler.parse_command("!help") == ("help", "")
        assert handler.parse_command("!summon") == ("summon", "")

    def test_parses_command_with_args(self, handler):
        assert handler.parse_command("!voice on") == ("voice", "on")
        assert handler.parse_command("!voice tts") == ("voice", "tts")

    def test_parses_command_with_extra_whitespace(self, handler):
        assert handler.parse_command("  !help  ") == ("help", "")

    def test_case_insensitive_command_name(self, handler):
        assert handler.parse_command("!HELP") == ("help", "")
        assert handler.parse_command("!Summon") == ("summon", "")

    def test_returns_none_for_non_command(self, handler):
        assert handler.parse_command("hello") is None
        assert handler.parse_command("no command here") is None

    def test_returns_none_for_empty_command(self, handler):
        assert handler.parse_command("!") is None
        assert handler.parse_command("   !   ") is None

    def test_returns_none_for_non_matching_prefix(self, handler):
        assert handler.parse_command("?help") is None
        assert handler.parse_command("#summon") is None

    def test_custom_prefix(self):
        cfg = _make_config(command_prefix="@")
        handler = CommandHandler(cfg)
        assert handler.parse_command("@help") == ("help", "")
        assert handler.parse_command("!help") is None

    def test_empty_prefix(self):
        cfg = _make_config(command_prefix="")
        handler = CommandHandler(cfg)
        assert handler.parse_command("help") == ("help", "")


class TestAuth:
    def test_is_allowed_user_empty_list_means_all_allowed(self):
        handler = CommandHandler(_make_config(allowed_users=[]))
        assert handler.is_allowed_user("anyone") is True

    def test_is_allowed_user_checks_list(self):
        handler = CommandHandler(_make_config(allowed_users=["Alice", "Bob"]))
        assert handler.is_allowed_user("Alice") is True
        assert handler.is_allowed_user("alice") is True
        assert handler.is_allowed_user("Charlie") is False

    def test_is_allowed_user_allow_all_flag(self):
        handler = CommandHandler(_make_config(allow_all_users=True, allowed_users=["Alice"]))
        assert handler.is_allowed_user("Charlie") is True

    def test_is_allowed_channel_empty_list_means_all_allowed(self):
        handler = CommandHandler(_make_config(allowed_channels=[]))
        assert handler.is_allowed_channel("anywhere") is True

    def test_is_allowed_channel_checks_list(self):
        handler = CommandHandler(_make_config(allowed_channels=["General", "Support"]))
        assert handler.is_allowed_channel("General") is True
        assert handler.is_allowed_channel("general") is True
        assert handler.is_allowed_channel("Restricted") is False


class TestHandleSummon:
    @pytest.fixture
    def handler(self):
        return CommandHandler(_make_config(allowed_channels=["General"]))

    def test_summon_returns_move_and_reply(self, handler):
        result = handler.handle("summon", "", _make_ctx(invoker_channel_id=42, invoker_channel_name="General"))
        assert result.move_to_channel_id == 42
        assert result.reply is not None
        assert "Summoned by TestUser" in result.reply

    def test_summon_blocked_by_disallowed_channel(self, handler):
        result = handler.handle("summon", "", _make_ctx(invoker_channel_id=99, invoker_channel_name="Restricted"))
        assert result.move_to_channel_id is None
        assert result.reply is not None
        assert "not in allowed channels" in result.reply

    def test_summon_with_no_invoker_channel(self, handler):
        result = handler.handle("summon", "", _make_ctx(invoker_channel_id=None, invoker_channel_name="unknown"))
        assert result.reply is not None
        assert "Cannot determine" in result.reply


class TestHandleLeave:
    @pytest.fixture
    def handler(self):
        return CommandHandler(_make_config())

    def test_leave_returns_move_to_home(self, handler):
        result = handler.handle("leave", "", _make_ctx(current_channel_id=42, home_channel_id=7))
        assert result.move_to_home is True
        assert result.reply is not None

    def test_leave_when_already_home(self, handler):
        result = handler.handle("leave", "", _make_ctx(current_channel_id=7, home_channel_id=7))
        assert result.move_to_home is False
        assert "Already in home" in result.reply

    def test_leave_without_home_channel(self, handler):
        result = handler.handle("leave", "", _make_ctx(home_channel_id=None))
        assert result.reply is not None
        assert "not configured" in result.reply


class TestHandleVoice:
    @pytest.fixture
    def handler(self):
        return CommandHandler(_make_config())

    def test_voice_on(self, handler):
        result = handler.handle("voice", "on", _make_ctx())
        assert result.set_voice_mode == "on"
        assert "Voice mode set to 'on'" in result.reply

    def test_voice_off(self, handler):
        result = handler.handle("voice", "off", _make_ctx())
        assert result.set_voice_mode == "off"
        assert "Voice mode set to 'off'" in result.reply

    def test_voice_tts(self, handler):
        result = handler.handle("voice", "tts", _make_ctx())
        assert result.set_voice_mode == "tts"
        assert "Voice mode set to 'tts'" in result.reply

    def test_voice_unknown_mode(self, handler):
        result = handler.handle("voice", "blah", _make_ctx())
        assert result.set_voice_mode is None
        assert "Unknown voice mode" in result.reply
        assert VOICE_HELP in result.reply

    def test_voice_empty_args(self, handler):
        result = handler.handle("voice", "", _make_ctx())
        assert result.set_voice_mode is None
        assert "Unknown voice mode" in result.reply

    @pytest.mark.parametrize("mode", ["On", "ON", "TTS", "Off"])
    def test_voice_case_insensitive(self, handler, mode):
        result = handler.handle("voice", mode, _make_ctx())
        assert result.set_voice_mode == mode.lower()


class TestHandleStatus:
    def test_status_reports_info(self):
        handler = CommandHandler(_make_config())
        handler.voice_mode = "tts"
        result = handler.handle("status", "", _make_ctx(
            current_channel_id=42, current_channel_name="Lounge",
            voice_mode="tts", uptime_seconds=3661.0,
        ))
        assert "Channel: Lounge (ID 42)" in result.reply
        assert "Voice mode: tts" in result.reply
        assert "1h 1m 1s" in result.reply

    def test_status_uptime_seconds_only(self):
        handler = CommandHandler(_make_config())
        result = handler.handle("status", "", _make_ctx(uptime_seconds=45.0))
        assert "45s" in result.reply

    def test_status_uptime_minutes(self):
        handler = CommandHandler(_make_config())
        result = handler.handle("status", "", _make_ctx(uptime_seconds=125.0))
        assert "2m 5s" in result.reply


class TestHandleHelp:
    def test_help_returns_commands(self):
        handler = CommandHandler(_make_config())
        result = handler.handle("help", "", _make_ctx())
        assert result.reply == COMMANDS_HELP


class TestHandleUnknown:
    def test_unknown_command_returns_help(self):
        handler = CommandHandler(_make_config())
        result = handler.handle("foobar", "", _make_ctx())
        assert result.reply == "Unknown command. Try !help"


class TestFormatUptime:
    def test_zero(self):
        assert CommandHandler._format_uptime(0) == "0s"

    def test_seconds_only(self):
        assert CommandHandler._format_uptime(30) == "30s"

    def test_minutes_only(self):
        assert CommandHandler._format_uptime(120) == "2m 0s"

    def test_minutes_and_seconds(self):
        assert CommandHandler._format_uptime(125) == "2m 5s"

    def test_hours_only(self):
        assert CommandHandler._format_uptime(3600) == "1h 0m 0s"

    def test_hours_minutes_seconds(self):
        assert CommandHandler._format_uptime(3661) == "1h 1m 1s"


class TestVoiceModeTracking:
    def test_default_voice_mode(self):
        handler = CommandHandler(_make_config())
        assert handler.voice_mode == "on"

    def test_set_voice_mode(self):
        handler = CommandHandler(_make_config())
        handler.voice_mode = "tts"
        assert handler.voice_mode == "tts"
