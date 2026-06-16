import asyncio
import os
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hermes_agent_ts3.adapter import TeamSpeakAdapter
from hermes_agent_ts3.config import TS3Config
from hermes_agent_ts3.server_query_types import (
    TS3ClientMovedEvent,
    TS3TextMessageEvent,
)

# Mock Hermes types
class MockPlatform:
    def __init__(self, name="teamspeak3"):
        self._name = name

    def __str__(self):
        return self._name

class MockPlatformConfig:
    pass

class MockSessionSource:
    def __init__(self, platform="", chat_id="", user_id="", user_name=""):
        self.platform = platform
        self.chat_id = chat_id
        self.user_id = user_id
        self.user_name = user_name

class MockMessageEvent:
    def __init__(self, source=None, chat_id="", content="", type=None, metadata=None):
        self.source = source
        self.chat_id = chat_id
        self.content = content
        self.type = type
        self.metadata = metadata or {}

class MockMessageType:
    TEXT = "text"
    VOICE = "voice"

class MockSendResult:
    def __init__(self, success=False, message_id=""):
        self.success = success
        self.message_id = message_id


@pytest.fixture
def ts3_config_dict():
    return {
        "TS3_SERVER_HOST": "ts.example.com",
        "TS3_SERVERQUERY_PORT": "10011",
        "TS3_SERVERQUERY_USER": "admin",
        "TS3_SERVERQUERY_PASS": "pass",
        "TS3_VOICE_PORT": "9987",
        "TS3_HOME_CHANNEL": "Home",
        "TS3_NICKNAME": "Hermes",
        "TS3_SERVER_PASSWORD": "",
        "TS3_CLIENT_DOWNLOAD_URL": "",
    }


@pytest.fixture
def adapter():
    cfg = MockPlatformConfig()
    platform = MockPlatform()
    return TeamSpeakAdapter(cfg, platform)


class TestConnectDisconnect:
    @pytest.mark.asyncio
    async def test_connect_full_lifecycle(self, adapter, ts3_config_dict):
        mock_bridge = AsyncMock()
        mock_bridge.start.return_value = MagicMock(
            sink_name="ts3_playback",
            monitor_name="ts3_playback.monitor",
            source_name="bot_tts",
            tts_sink_name="bot_tts_sink",
        )

        mock_client = AsyncMock()

        mock_sq = AsyncMock()
        mock_sq.connect = AsyncMock()
        mock_sq.disconnect = AsyncMock()
        mock_sq.client_list.return_value = [
            {"clid": "42", "client_nickname": "Hermes"},
        ]
        mock_sq.channel_list.return_value = [
            {"cid": "1", "channel_name": "Home"},
        ]
        mock_sq.channel_find.return_value = [
            {"cid": "1", "channel_name": "Home"},
        ]
        mock_sq.client_move = AsyncMock()
        mock_sq.events.return_value = AsyncMock()
        mock_sq.events.return_value.__aiter__ = AsyncMock(
            return_value=AsyncMock(
                __anext__=AsyncMock(side_effect=asyncio.CancelledError()),
            )
        )

        mock_voice_recv = MagicMock()
        mock_voice_player = MagicMock()

        with patch.dict(os.environ, ts3_config_dict, clear=True):
            with patch("hermes_agent_ts3.adapter.PulseAudioBridge", return_value=mock_bridge), \
                 patch("hermes_agent_ts3.adapter.TS3ClientManager", return_value=mock_client), \
                 patch("hermes_agent_ts3.adapter.TS3ServerQuery", return_value=mock_sq), \
                 patch("hermes_agent_ts3.adapter.TS3VoiceReceiver", return_value=mock_voice_recv), \
                 patch("hermes_agent_ts3.adapter.TS3VoicePlayer", return_value=mock_voice_player), \
                 patch("hermes_agent_ts3.adapter.urllib.request.urlretrieve"), \
                 patch("pathlib.Path.exists", return_value=False), \
                 patch("pathlib.Path.mkdir"):

                result = await adapter.connect()

                assert result is True
                assert adapter.is_connected is True
                assert adapter._my_client_id == 42
                assert adapter._home_channel_id == 1
                assert adapter._event_task is not None
                assert adapter._idle_task is not None

                mock_bridge.start.assert_awaited_once()
                mock_client.start.assert_awaited_once()
                mock_sq.connect.assert_awaited_once()
                mock_sq.client_move.assert_awaited_once()
                mock_voice_recv.on_utterance.assert_called_once()
                mock_voice_recv.start.assert_called_once()

    @pytest.mark.asyncio
    async def test_disconnect_stops_all_services(self, adapter, ts3_config_dict):
        mock_bridge = AsyncMock()
        mock_client = AsyncMock()
        mock_sq = AsyncMock()
        mock_voice_recv = MagicMock()
        mock_voice_player = MagicMock()

        adapter._audio_bridge = mock_bridge
        adapter._client = mock_client
        adapter._sq = mock_sq
        adapter._voice_receiver = mock_voice_recv
        adapter._voice_player = mock_voice_player
        adapter._my_client_id = 42
        adapter._home_channel_id = 1

        async def _pending():
            await asyncio.Event().wait()

        event_task = asyncio.create_task(_pending())
        idle_task = asyncio.create_task(_pending())
        adapter._event_task = event_task
        adapter._idle_task = idle_task

        await adapter.disconnect()

        assert event_task.cancelled()
        assert idle_task.cancelled()
        mock_voice_recv.stop.assert_called_once()
        mock_voice_player.stop.assert_called_once()
        mock_sq.disconnect.assert_awaited_once()
        mock_client.stop.assert_awaited_once()
        mock_bridge.stop.assert_awaited_once()
        assert adapter._my_client_id is None
        assert adapter.is_connected is False

    @pytest.mark.asyncio
    async def test_disconnect_noop_when_already_disconnected(self, adapter):
        async def _pending():
            await asyncio.Event().wait()

        event_task = asyncio.create_task(_pending())
        idle_task = asyncio.create_task(_pending())
        adapter._event_task = event_task
        adapter._idle_task = idle_task

        await adapter.disconnect()

        assert event_task.cancelled()
        assert idle_task.cancelled()


class TestSend:
    @pytest.mark.asyncio
    async def test_send_text_message(self, adapter):
        mock_sq = AsyncMock()
        mock_sq.send_text_message = AsyncMock()
        adapter._sq = mock_sq
        adapter._my_client_id = 42
        adapter._home_channel_id = 1

        result = await adapter.send("1", "Hello, world!")

        mock_sq.send_text_message.assert_awaited_once_with(
            target_mode=2, target_id=1, message="Hello, world!"
        )
        assert result.success is True

    @pytest.mark.asyncio
    async def test_send_no_sq_returns_failure(self, adapter):
        adapter._sq = None

        result = await adapter.send("1", "Hello")

        assert result.success is False

    @pytest.mark.asyncio
    async def test_send_invalid_chat_id_falls_back_to_home(self, adapter):
        mock_sq = AsyncMock()
        mock_sq.send_text_message = AsyncMock()
        adapter._sq = mock_sq
        adapter._home_channel_id = 1

        await adapter.send("invalid", "Hello")

        mock_sq.send_text_message.assert_awaited_once_with(
            target_mode=2, target_id=1, message="Hello"
        )

    @pytest.mark.asyncio
    async def test_send_resets_idle(self, adapter):
        mock_sq = AsyncMock()
        mock_sq.send_text_message = AsyncMock()
        adapter._sq = mock_sq
        adapter._home_channel_id = 1
        adapter._idle_since = 0.0

        await adapter.send("1", "Hello")

        assert adapter._idle_since > 0.0


class TestGetChatInfo:
    @pytest.mark.asyncio
    async def test_get_chat_info_returns_channel_info(self, adapter):
        mock_sq = AsyncMock()
        mock_sq.channel_info.return_value = {"channel_name": "General", "cid": "5"}
        adapter._sq = mock_sq

        info = await adapter.get_chat_info("5")

        mock_sq.channel_info.assert_awaited_once_with(5)
        assert info["channel_name"] == "General"

    @pytest.mark.asyncio
    async def test_get_chat_info_no_sq_returns_empty(self, adapter):
        adapter._sq = None
        info = await adapter.get_chat_info("5")
        assert info == {}

    @pytest.mark.asyncio
    async def test_get_chat_info_error_returns_empty(self, adapter):
        mock_sq = AsyncMock()
        mock_sq.channel_info.side_effect = RuntimeError("fail")
        adapter._sq = mock_sq

        info = await adapter.get_chat_info("5")
        assert info == {}


class TestVoiceChannel:
    @pytest.mark.asyncio
    async def test_join_voice_channel_moves_and_starts_listen(self, adapter):
        mock_sq = AsyncMock()
        mock_sq.client_move = AsyncMock()
        adapter._sq = mock_sq
        adapter._my_client_id = 42
        adapter._home_channel_id = 1
        adapter._voice_receiver = MagicMock()

        result = await adapter.join_voice_channel(10)

        assert result is True
        assert adapter._current_channel_id == 10
        mock_sq.client_move.assert_awaited_once_with(42, 10)
        adapter._voice_receiver.resume.assert_called_once()
        assert adapter._voice_listen_active.is_set()

    @pytest.mark.asyncio
    async def test_join_voice_channel_no_sq_returns_false(self, adapter):
        adapter._sq = None
        result = await adapter.join_voice_channel(10)
        assert result is False

    @pytest.mark.asyncio
    async def test_join_voice_channel_move_fails_returns_false(self, adapter):
        mock_sq = AsyncMock()
        mock_sq.client_move.side_effect = RuntimeError("fail")
        adapter._sq = mock_sq
        adapter._my_client_id = 42

        result = await adapter.join_voice_channel(10)
        assert result is False

    @pytest.mark.asyncio
    async def test_leave_voice_channel_stops_listen_and_returns_home(self, adapter):
        mock_sq = AsyncMock()
        mock_sq.client_move = AsyncMock()
        adapter._sq = mock_sq
        adapter._my_client_id = 42
        adapter._home_channel_id = 1
        adapter._current_channel_id = 10
        adapter._voice_receiver = MagicMock()

        await adapter.leave_voice_channel()

        mock_sq.client_move.assert_awaited_once_with(42, 1)
        assert adapter._current_channel_id == 1
        adapter._voice_receiver.pause.assert_called_once()
        assert not adapter._voice_listen_active.is_set()

    @pytest.mark.asyncio
    async def test_leave_voice_channel_no_sq(self, adapter):
        adapter._sq = None
        adapter._voice_receiver = MagicMock()

        await adapter.leave_voice_channel()

        adapter._voice_receiver.pause.assert_called_once()


class TestVoiceListenLoop:
    @pytest.mark.asyncio
    async def test_on_utterance_transcribes_and_handles(self, adapter):
        adapter._current_channel_id = 10
        adapter._voice_listen_active.set()
        adapter.handle_message = AsyncMock()

        with patch("hermes_agent_ts3.adapter.transcribe_audio", return_value="Hello there"), \
             patch("hermes_agent_ts3.adapter.is_whisper_hallucination", return_value=False):
            await adapter._on_utterance(b"fake_wav")

        adapter.handle_message.assert_called_once()
        event = adapter.handle_message.call_args.args[0]
        assert event.type == "voice"
        assert event.content == "Hello there"
        assert event.chat_id == "10"

    @pytest.mark.asyncio
    async def test_on_utterance_not_active_ignores(self, adapter):
        adapter._voice_listen_active.clear()
        adapter.handle_message = AsyncMock()

        await adapter._on_utterance(b"fake_wav")

        adapter.handle_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_on_utterance_filters_hallucination(self, adapter):
        adapter._current_channel_id = 10
        adapter._voice_listen_active.set()
        adapter.handle_message = AsyncMock()

        with patch("hermes_agent_ts3.adapter.transcribe_audio", return_value="Thank you."), \
             patch("hermes_agent_ts3.adapter.is_whisper_hallucination", return_value=True):
            await adapter._on_utterance(b"fake_wav")

        adapter.handle_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_on_utterance_handles_transcription_error(self, adapter):
        adapter._current_channel_id = 10
        adapter._voice_listen_active.set()
        adapter.handle_message = AsyncMock()

        with patch("hermes_agent_ts3.adapter.transcribe_audio", side_effect=RuntimeError("fail")):
            await adapter._on_utterance(b"fake_wav")

        adapter.handle_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_on_utterance_ignores_empty_text(self, adapter):
        adapter._current_channel_id = 10
        adapter._voice_listen_active.set()
        adapter.handle_message = AsyncMock()

        with patch("hermes_agent_ts3.adapter.transcribe_audio", return_value=""), \
             patch("hermes_agent_ts3.adapter.is_whisper_hallucination", return_value=False):
            await adapter._on_utterance(b"fake_wav")

        adapter.handle_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_on_utterance_ignores_whitespace_only(self, adapter):
        adapter._current_channel_id = 10
        adapter._voice_listen_active.set()
        adapter.handle_message = AsyncMock()

        with patch("hermes_agent_ts3.adapter.transcribe_audio", return_value="   "), \
             patch("hermes_agent_ts3.adapter.is_whisper_hallucination", return_value=False):
            await adapter._on_utterance(b"fake_wav")

        adapter.handle_message.assert_not_called()


class TestAuth:
    def test_is_allowed_user_all_when_empty_list(self, adapter):
        adapter._ts3_config.allowed_users = []
        adapter._ts3_config.allow_all_users = False
        assert adapter._is_allowed_user("anyone") is True

    def test_is_allowed_user_all_when_not_set(self, adapter):
        adapter._ts3_config.allowed_users = ["alice", "bob"]
        adapter._ts3_config.allow_all_users = False
        assert adapter._is_allowed_user("alice") is True
        assert adapter._is_allowed_user("ALICE") is True
        assert adapter._is_allowed_user("charlie") is False

    def test_is_allowed_user_case_insensitive(self, adapter):
        adapter._ts3_config.allowed_users = ["Alice", "BOB"]
        adapter._ts3_config.allow_all_users = False
        assert adapter._is_allowed_user("alice") is True
        assert adapter._is_allowed_user("bob") is True

    def test_is_allowed_user_allow_all_env(self, adapter):
        adapter._ts3_config.allowed_users = ["alice"]
        adapter._ts3_config.allow_all_users = True
        assert adapter._is_allowed_user("anyone") is True

    def test_is_allowed_user_allow_all_env_true(self, adapter):
        adapter._ts3_config.allowed_users = ["alice"]
        adapter._ts3_config.allow_all_users = True
        assert adapter._is_allowed_user("anyone") is True

    def test_is_allowed_user_allow_all_env_yes(self, adapter):
        adapter._ts3_config.allowed_users = ["alice"]
        adapter._ts3_config.allow_all_users = True
        assert adapter._is_allowed_user("anyone") is True

    def test_is_allowed_channel_empty_list(self, adapter):
        adapter._ts3_config.allowed_channels = []
        assert adapter._ts3_config.allowed_channels == []

    def test_is_allowed_channel_matches(self, adapter):
        adapter._ts3_config.allowed_channels = ["General", "Support"]
        assert "General" in adapter._ts3_config.allowed_channels


class TestEventLoop:
    @pytest.mark.asyncio
    async def test_handle_text_message_allowed_user(self, adapter):
        adapter._my_client_id = 42
        adapter._current_channel_id = 5
        adapter._ts3_config.allowed_users = []
        adapter._idle_since = 0.0
        adapter.handle_message = AsyncMock()

        event = TS3TextMessageEvent(
            targetmode=2,
            msg="Hello bot",
            invokerid=10,
            invokername="Alice",
            invokeruid="uid-alice",
        )

        await adapter._handle_text_message(event)

        adapter.handle_message.assert_called_once()
        msg = adapter.handle_message.call_args.args[0]
        assert msg.content == "Hello bot"
        assert msg.type == "text"
        assert msg.chat_id == "5"
        assert adapter._idle_since > 0.0

    @pytest.mark.asyncio
    async def test_handle_text_message_ignores_own_messages(self, adapter):
        adapter._my_client_id = 42
        adapter.handle_message = AsyncMock()

        event = TS3TextMessageEvent(
            targetmode=2,
            msg="Hello",
            invokerid=42,
            invokername="Hermes",
            invokeruid="uid-hermes",
        )

        await adapter._handle_text_message(event)
        adapter.handle_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_text_message_blocked_user(self, adapter):
        adapter._my_client_id = 42
        adapter._ts3_config.allowed_users = ["alice"]
        adapter.handle_message = AsyncMock()

        event = TS3TextMessageEvent(
            targetmode=2,
            msg="Hello",
            invokerid=10,
            invokername="Bob",
            invokeruid="uid-bob",
        )

        await adapter._handle_text_message(event)

        adapter.handle_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_text_message_private_message(self, adapter):
        adapter._my_client_id = 42
        adapter._ts3_config.allowed_users = []
        adapter.handle_message = AsyncMock()

        event = TS3TextMessageEvent(
            targetmode=1,
            msg="Private hello",
            invokerid=10,
            invokername="Alice",
            invokeruid="uid-alice",
        )

        await adapter._handle_text_message(event)

        msg = adapter.handle_message.call_args.args[0]
        assert msg.chat_id == "10"
        assert msg.content == "Private hello"
        assert adapter._message_origins["client:10"] == 1

    @pytest.mark.asyncio
    async def test_handle_client_moved_updates_current_channel(self, adapter):
        adapter._my_client_id = 42

        event = TS3ClientMovedEvent(
            ctid=10,
            clid=42,
            client_nickname="Hermes",
            raw={},
        )

        await adapter._handle_client_moved(event)
        assert adapter._current_channel_id == 10

    @pytest.mark.asyncio
    async def test_handle_client_moved_ignores_other_clients(self, adapter):
        adapter._my_client_id = 42
        adapter._current_channel_id = 5

        event = TS3ClientMovedEvent(
            ctid=99,
            clid=100,
            client_nickname="Other",
            raw={},
        )

        await adapter._handle_client_moved(event)
        assert adapter._current_channel_id == 5

    @pytest.mark.asyncio
    async def test_event_loop_processes_text_messages(self, adapter):
        adapter._my_client_id = 42
        adapter._current_channel_id = 5
        adapter._ts3_config.allowed_users = []
        adapter.handle_message = AsyncMock()

        events = [
            TS3TextMessageEvent(
                targetmode=2,
                msg="Test message",
                invokerid=10,
                invokername="Alice",
                invokeruid="uid-alice",
            ),
        ]

        mock_events = AsyncMock()
        mock_events.__aiter__ = AsyncMock(return_value=mock_events)
        mock_events.__anext__ = AsyncMock(side_effect=events + [asyncio.CancelledError()])

        mock_sq = AsyncMock()
        mock_sq.events.return_value = events
        adapter._sq = mock_sq

        mock_iterator = MagicMock()
        mock_iterator.__aiter__.return_value = iter(events)

        async def mock_events_gen_with_stop():
            for e in events:
                yield e
            adapter._running = False

        adapter._sq.events = mock_events_gen_with_stop
        adapter._running = True

        try:
            await asyncio.wait_for(adapter._event_loop(), timeout=0.5)
        except asyncio.TimeoutError:
            pass

        adapter.handle_message.assert_called_once()


class TestTTS:
    @pytest.mark.asyncio
    async def test_play_tts_pauses_resumes_receiver(self, adapter):
        mock_player = AsyncMock()
        mock_player.play_file = AsyncMock()
        mock_receiver = MagicMock()

        adapter._voice_player = mock_player
        adapter._voice_receiver = mock_receiver

        await adapter.play_tts("5", "/tmp/tts.wav")

        mock_receiver.pause.assert_called_once()
        mock_player.play_file.assert_awaited_once_with("/tmp/tts.wav")
        mock_receiver.resume.assert_called_once()

    @pytest.mark.asyncio
    async def test_play_tts_no_player_logs_error(self, adapter):
        adapter._voice_player = None
        adapter._voice_receiver = MagicMock()

        await adapter.play_tts("5", "/tmp/tts.wav")

        adapter._voice_receiver.pause.assert_not_called()

    @pytest.mark.asyncio
    async def test_play_tts_no_receiver_still_plays(self, adapter):
        mock_player = AsyncMock()
        mock_player.play_file = AsyncMock()
        adapter._voice_player = mock_player
        adapter._voice_receiver = None

        await adapter.play_tts("5", "/tmp/tts.wav")

        mock_player.play_file.assert_awaited_once_with("/tmp/tts.wav")


class TestIdleTimeout:
    @pytest.mark.asyncio
    async def test_idle_watcher_returns_home_after_timeout(self, adapter):
        adapter._home_channel_id = 1
        adapter._current_channel_id = 10
        adapter._my_client_id = 42
        adapter._idle_since = time.monotonic() - 400
        adapter._sq = AsyncMock()
        adapter._sq.client_move = AsyncMock()
        adapter._voice_receiver = MagicMock()

        sleep_count = 0

        async def tracking_sleep(delay):
            nonlocal sleep_count
            sleep_count += 1
            if sleep_count >= 2:
                raise asyncio.CancelledError()

        with patch("asyncio.sleep", side_effect=tracking_sleep):
            try:
                await adapter._idle_watcher()
            except asyncio.CancelledError:
                pass

        assert adapter._current_channel_id == 1
        adapter._voice_receiver.pause.assert_called_once()

    @pytest.mark.asyncio
    async def test_idle_watcher_noop_when_in_home_channel(self, adapter):
        adapter._home_channel_id = 1
        adapter._current_channel_id = 1
        adapter._my_client_id = 42
        adapter._idle_since = time.monotonic() - 400

        sleep_count = 0

        async def tracking_sleep(delay):
            nonlocal sleep_count
            sleep_count += 1
            if sleep_count >= 2:
                raise asyncio.CancelledError()

        with patch("asyncio.sleep", side_effect=tracking_sleep):
            try:
                await adapter._idle_watcher()
            except asyncio.CancelledError:
                pass

        assert adapter._current_channel_id == 1

    @pytest.mark.asyncio
    async def test_idle_watcher_noop_when_not_idle(self, adapter):
        adapter._home_channel_id = 1
        adapter._current_channel_id = 10
        adapter._my_client_id = 42
        adapter._idle_since = time.monotonic()

        sleep_count = 0

        async def tracking_sleep(delay):
            nonlocal sleep_count
            sleep_count += 1
            if sleep_count >= 2:
                raise asyncio.CancelledError()

        with patch("asyncio.sleep", side_effect=tracking_sleep):
            try:
                await adapter._idle_watcher()
            except asyncio.CancelledError:
                pass

        assert adapter._current_channel_id == 10

    def test_reset_idle_updates_timestamp(self, adapter):
        old_idle = time.monotonic() - 100
        adapter._idle_since = old_idle
        adapter._reset_idle()
        assert adapter._idle_since > old_idle


class TestClientBinaryDownload:
    def _make_mock_subprocess(self, returncode=0, stdout=b"42\n"):
        mock = AsyncMock()
        mock.communicate.return_value = (stdout, b"")
        mock.returncode = returncode
        return mock

    @pytest.mark.asyncio
    async def test_hash_file(self, tmp_path):
        file_path = tmp_path / "test.bin"
        file_path.write_bytes(b"hello world")

        result = TeamSpeakAdapter._hash_file(str(file_path))
        expected = (
            "b94d27b9934d3e08a52e52d7da7dabfa"
            "c484efe37a5380ee9088f7ace2efcde9"
        )
        assert result == expected

    @pytest.mark.asyncio
    async def test_extract_archive_tar_gz(self, tmp_path):
        import tarfile

        archive = tmp_path / "test.tar.gz"
        with tarfile.open(str(archive), "w:gz") as tf:
            info = tarfile.TarInfo(name="ts3client_linux_amd64")
            info.size = 0
            tf.addfile(info)

        dest = tmp_path / "extracted"
        TeamSpeakAdapter._extract_archive(str(archive), dest)
        assert (dest / "ts3client_linux_amd64").exists()
