import asyncio
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from hermes_agent_ts3.audio_bridge import PulseAudioBridge, PulseAudioDeviceInfo


class TestPulseAudioDeviceInfo:
    def test_default_module_ids(self):
        info = PulseAudioDeviceInfo(
            sink_name="sink1",
            monitor_name="sink1.monitor",
            source_name="src1",
            tts_sink_name="tts1",
        )
        assert info.module_ids == []
        assert info.sink_name == "sink1"
        assert info.monitor_name == "sink1.monitor"
        assert info.source_name == "src1"
        assert info.tts_sink_name == "tts1"


class TestPulseAudioBridgeInit:
    def test_default_values(self):
        bridge = PulseAudioBridge()
        assert bridge._sink_name == "ts3_playback"
        assert bridge._source_name == "bot_tts"
        assert bridge._tts_sink_name == "bot_tts_sink"
        assert bridge._pulse_server == ""
        assert bridge._module_ids == []
        assert bridge._device_info is None

    def test_custom_names(self):
        bridge = PulseAudioBridge(
            pulse_server="unix:/tmp/pulse",
            sink_name="custom_sink",
            source_name="custom_source",
            tts_sink_name="custom_tts_sink",
        )
        assert bridge._pulse_server == "unix:/tmp/pulse"
        assert bridge._sink_name == "custom_sink"
        assert bridge._source_name == "custom_source"
        assert bridge._tts_sink_name == "custom_tts_sink"


class TestBuildEnv:
    def test_build_env_no_pulse_server(self):
        bridge = PulseAudioBridge()
        env = bridge._build_env()
        assert "PULSE_SERVER" not in env

    def test_build_env_with_pulse_server(self):
        bridge = PulseAudioBridge(pulse_server="unix:/tmp/pulse")
        env = bridge._build_env()
        assert env["PULSE_SERVER"] == "unix:/tmp/pulse"


class TestPactl:
    @pytest.mark.asyncio
    async def test_pactl_returns_module_id(self):
        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (b"42\n", b"")
        mock_proc.returncode = 0

        bridge = PulseAudioBridge()
        with patch(
            "hermes_agent_ts3.audio_bridge.asyncio.create_subprocess_exec",
            return_value=mock_proc,
        ) as mock_exec:
            result = await bridge._pactl("load-module", "module-null-sink", "sink_name=foo")
            assert result == 42
            mock_proc.communicate.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_pactl_nonzero_raises(self):
        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (b"", b"some error")
        mock_proc.returncode = 1

        bridge = PulseAudioBridge()
        with patch(
            "hermes_agent_ts3.audio_bridge.asyncio.create_subprocess_exec",
            return_value=mock_proc,
        ):
            with pytest.raises(RuntimeError, match="failed"):
                await bridge._pactl("load-module", "module-null-sink")

    @pytest.mark.asyncio
    async def test_pactl_invalid_output_returns_minus_one(self):
        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (b"not_a_number\n", b"")
        mock_proc.returncode = 0

        bridge = PulseAudioBridge()
        with patch(
            "hermes_agent_ts3.audio_bridge.asyncio.create_subprocess_exec",
            return_value=mock_proc,
        ):
            result = await bridge._pactl("load-module", "module-null-sink")
            assert result == -1

    @pytest.mark.asyncio
    async def test_pactl_passes_pulse_server_env(self):
        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (b"99\n", b"")
        mock_proc.returncode = 0

        bridge = PulseAudioBridge(pulse_server="unix:/tmp/pulse")
        with patch(
            "hermes_agent_ts3.audio_bridge.asyncio.create_subprocess_exec",
            return_value=mock_proc,
        ) as mock_exec:
            await bridge._pactl("load-module", "module-null-sink")
            kwargs = mock_exec.call_args.kwargs
            assert kwargs["env"]["PULSE_SERVER"] == "unix:/tmp/pulse"


class TestRunPactl:
    @pytest.mark.asyncio
    async def test_run_pactl_returns_output(self):
        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (b"sink1\tsink2\n", b"")
        mock_proc.returncode = 0

        bridge = PulseAudioBridge()
        with patch(
            "hermes_agent_ts3.audio_bridge.asyncio.create_subprocess_exec",
            return_value=mock_proc,
        ):
            result = await bridge._run_pactl("list", "short", "sinks")
            assert result == "sink1\tsink2\n"

    @pytest.mark.asyncio
    async def test_run_pactl_nonzero_returns_empty_string(self):
        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (b"", b"error")
        mock_proc.returncode = 1

        bridge = PulseAudioBridge()
        with patch(
            "hermes_agent_ts3.audio_bridge.asyncio.create_subprocess_exec",
            return_value=mock_proc,
        ):
            result = await bridge._run_pactl("list", "short", "sinks")
            assert result == ""


class TestFindExistingModules:
    def _make_list_output(self, names):
        lines = ["1\t" + name for name in names]
        return ("\n".join(lines) + "\n").encode()

    @pytest.mark.asyncio
    async def test_existing_all_devices(self):
        sinks_stdout = self._make_list_output(["ts3_playback", "bot_tts_sink"])
        sources_stdout = self._make_list_output(["bot_tts.monitor", "bot_tts"])

        mock_sinks = AsyncMock()
        mock_sinks.communicate.return_value = (sinks_stdout, b"")
        mock_sources = AsyncMock()
        mock_sources.communicate.return_value = (sources_stdout, b"")

        bridge = PulseAudioBridge()
        with patch(
            "hermes_agent_ts3.audio_bridge.asyncio.create_subprocess_exec",
            side_effect=[mock_sinks, mock_sources],
        ):
            result = await bridge._find_existing_modules()
            assert result is not None
            assert result.sink_name == "ts3_playback"
            assert result.monitor_name == "ts3_playback.monitor"
            assert result.source_name == "bot_tts"
            assert result.tts_sink_name == "bot_tts_sink"

    @pytest.mark.asyncio
    async def test_no_existing_devices(self):
        sinks_stdout = self._make_list_output([])
        sources_stdout = self._make_list_output([])

        mock_sinks = AsyncMock()
        mock_sinks.communicate.return_value = (sinks_stdout, b"")
        mock_sources = AsyncMock()
        mock_sources.communicate.return_value = (sources_stdout, b"")

        bridge = PulseAudioBridge()
        with patch(
            "hermes_agent_ts3.audio_bridge.asyncio.create_subprocess_exec",
            side_effect=[mock_sinks, mock_sources],
        ):
            result = await bridge._find_existing_modules()
            assert result is None

    @pytest.mark.asyncio
    async def test_partial_devices_returns_none(self):
        sinks_stdout = self._make_list_output(["ts3_playback"])
        sources_stdout = self._make_list_output([])

        mock_sinks = AsyncMock()
        mock_sinks.communicate.return_value = (sinks_stdout, b"")
        mock_sources = AsyncMock()
        mock_sources.communicate.return_value = (sources_stdout, b"")

        bridge = PulseAudioBridge()
        with patch(
            "hermes_agent_ts3.audio_bridge.asyncio.create_subprocess_exec",
            side_effect=[mock_sinks, mock_sources],
        ):
            result = await bridge._find_existing_modules()
            assert result is None

    @pytest.mark.asyncio
    async def test_pactl_timeout_returns_none(self):
        mock_sinks = AsyncMock()
        mock_sinks.communicate.side_effect = asyncio.TimeoutError()
        mock_sources = AsyncMock()
        mock_sources.communicate.return_value = (b"", b"")

        bridge = PulseAudioBridge()
        with patch(
            "hermes_agent_ts3.audio_bridge.asyncio.create_subprocess_exec",
            side_effect=[mock_sinks, mock_sources],
        ):
            result = await bridge._find_existing_modules()
            assert result is None

    @pytest.mark.asyncio
    async def test_pactl_not_found_returns_none(self):
        bridge = PulseAudioBridge()
        with patch(
            "hermes_agent_ts3.audio_bridge.asyncio.create_subprocess_exec",
            side_effect=FileNotFoundError(),
        ):
            result = await bridge._find_existing_modules()
            assert result is None


class TestStart:
    def _make_pactl_mock(self, returncode=0, stdout=b"42\n"):
        mock = AsyncMock()
        mock.communicate.return_value = (stdout, b"")
        mock.returncode = returncode
        return mock

    @pytest.mark.asyncio
    async def test_start_idempotent_when_devices_exist(self):
        sinks_stdout = ("1\tts3_playback\n2\tbot_tts_sink\n").encode()
        sources_stdout = ("1\tbot_tts.monitor\n2\tbot_tts\n").encode()

        mock_sinks = AsyncMock()
        mock_sinks.communicate.return_value = (sinks_stdout, b"")
        mock_sources = AsyncMock()
        mock_sources.communicate.return_value = (sources_stdout, b"")

        bridge = PulseAudioBridge()
        with patch(
            "hermes_agent_ts3.audio_bridge.asyncio.create_subprocess_exec",
            side_effect=[mock_sinks, mock_sources],
        ) as mock_exec:
            result = await bridge.start()
            assert result.sink_name == "ts3_playback"
            assert result.source_name == "bot_tts"
            assert bridge._module_ids == []
            assert mock_exec.call_count == 2

    @pytest.mark.asyncio
    async def test_start_creates_new_devices(self):
        empty = "".encode()
        no_sinks = AsyncMock()
        no_sinks.communicate.return_value = (empty, b"")
        no_sources = AsyncMock()
        no_sources.communicate.return_value = (empty, b"")

        pactl_sink = self._make_pactl_mock(stdout=b"1\n")
        pactl_tts = self._make_pactl_mock(stdout=b"2\n")
        pactl_source = self._make_pactl_mock(stdout=b"3\n")

        bridge = PulseAudioBridge()
        with patch(
            "hermes_agent_ts3.audio_bridge.asyncio.create_subprocess_exec",
            side_effect=[no_sinks, no_sources, pactl_sink, pactl_tts, pactl_source],
        ):
            result = await bridge.start()
            assert result.sink_name == "ts3_playback"
            assert result.monitor_name == "ts3_playback.monitor"
            assert result.source_name == "bot_tts"
            assert result.tts_sink_name == "bot_tts_sink"
            assert result.module_ids == [1, 2, 3]
            assert bridge._module_ids == [1, 2, 3]
            assert bridge._device_info == result

    @pytest.mark.asyncio
    async def test_start_rollback_on_error(self):
        empty = "".encode()
        no_sinks = AsyncMock()
        no_sinks.communicate.return_value = (empty, b"")
        no_sources = AsyncMock()
        no_sources.communicate.return_value = (empty, b"")

        pactl_sink = self._make_pactl_mock(stdout=b"1\n")
        pactl_fail = self._make_pactl_mock(returncode=1, stdout=b"")
        pactl_unload = self._make_pactl_mock(stdout=b"0\n")

        bridge = PulseAudioBridge()
        with patch(
            "hermes_agent_ts3.audio_bridge.asyncio.create_subprocess_exec",
            side_effect=[no_sinks, no_sources, pactl_sink, pactl_fail, pactl_unload],
        ) as mock_exec:
            with pytest.raises(RuntimeError):
                await bridge.start()
            assert bridge._module_ids == []
            assert bridge._device_info is None
            assert mock_exec.call_count == 5
            unload_call = mock_exec.call_args_list[4]
            assert unload_call.args[1] == "unload-module"
            assert unload_call.args[2] == "1"

    @pytest.mark.asyncio
    async def test_start_respects_custom_names(self):
        empty = "".encode()
        no_sinks = AsyncMock()
        no_sinks.communicate.return_value = (empty, b"")
        no_sources = AsyncMock()
        no_sources.communicate.return_value = (empty, b"")

        p1 = self._make_pactl_mock(stdout=b"10\n")
        p2 = self._make_pactl_mock(stdout=b"20\n")
        p3 = self._make_pactl_mock(stdout=b"30\n")

        bridge = PulseAudioBridge(sink_name="custom_sink", source_name="custom_source", tts_sink_name="custom_tts")
        with patch(
            "hermes_agent_ts3.audio_bridge.asyncio.create_subprocess_exec",
            side_effect=[no_sinks, no_sources, p1, p2, p3],
        ) as mock_exec:
            result = await bridge.start()
            assert result.sink_name == "custom_sink"
            assert result.monitor_name == "custom_sink.monitor"
            assert result.source_name == "custom_source"
            assert result.tts_sink_name == "custom_tts"

            calls = mock_exec.call_args_list[2:]
            assert "sink_name=custom_sink" in " ".join(calls[0].args)
            assert "sink_name=custom_tts" in " ".join(calls[1].args)
            assert "source_name=custom_source" in " ".join(calls[2].args)


class TestStop:
    def _make_pactl_mock(self, returncode=0, stdout=b"0\n"):
        mock = AsyncMock()
        mock.communicate.return_value = (stdout, b"")
        mock.returncode = returncode
        return mock

    @pytest.mark.asyncio
    async def test_stop_unloads_all_modules(self):
        mock1 = self._make_pactl_mock()
        mock2 = self._make_pactl_mock()
        mock3 = self._make_pactl_mock()

        bridge = PulseAudioBridge()
        bridge._module_ids = [1, 2, 3]

        with patch(
            "hermes_agent_ts3.audio_bridge.asyncio.create_subprocess_exec",
            side_effect=[mock1, mock2, mock3],
        ) as mock_exec:
            await bridge.stop()
            assert bridge._module_ids == []
            assert bridge._device_info is None
            assert mock_exec.call_count == 3
            calls = mock_exec.call_args_list
            assert calls[0].args[1] == "unload-module"
            assert calls[0].args[2] == "3"
            assert calls[1].args[2] == "2"
            assert calls[2].args[2] == "1"

    @pytest.mark.asyncio
    async def test_stop_empty_modules_noop(self):
        bridge = PulseAudioBridge()
        with patch(
            "hermes_agent_ts3.audio_bridge.asyncio.create_subprocess_exec",
        ) as mock_exec:
            await bridge.stop()
            mock_exec.assert_not_called()

    @pytest.mark.asyncio
    async def test_stop_continues_on_unload_failure(self):
        mock_fail = self._make_pactl_mock(returncode=1, stdout=b"")
        mock_ok = self._make_pactl_mock()

        bridge = PulseAudioBridge()
        bridge._module_ids = [1, 2]

        with patch(
            "hermes_agent_ts3.audio_bridge.asyncio.create_subprocess_exec",
            side_effect=[mock_fail, mock_ok],
        ) as mock_exec:
            await bridge.stop()
            assert bridge._module_ids == []
            assert mock_exec.call_count == 2


class TestVerify:
    def _make_pactl_mock(self, stdout=b"", returncode=0):
        mock = AsyncMock()
        mock.communicate.return_value = (stdout, b"")
        mock.returncode = returncode
        return mock

    @pytest.mark.asyncio
    async def test_verify_all_present(self):
        sinks = ("1\tts3_playback\n2\tbot_tts_sink\n").encode()
        sources = ("1\tbot_tts\n").encode()

        mock_sinks = self._make_pactl_mock(stdout=sinks)
        mock_sources = self._make_pactl_mock(stdout=sources)

        bridge = PulseAudioBridge()
        with patch(
            "hermes_agent_ts3.audio_bridge.asyncio.create_subprocess_exec",
            side_effect=[mock_sinks, mock_sources],
        ):
            assert await bridge.verify() is True

    @pytest.mark.asyncio
    async def test_verify_none_present(self):
        mock_sinks = self._make_pactl_mock(stdout="".encode())
        mock_sources = self._make_pactl_mock(stdout="".encode())

        bridge = PulseAudioBridge()
        with patch(
            "hermes_agent_ts3.audio_bridge.asyncio.create_subprocess_exec",
            side_effect=[mock_sinks, mock_sources],
        ):
            assert await bridge.verify() is False

    @pytest.mark.asyncio
    async def test_verify_partial_returns_false(self):
        sinks = ("1\tts3_playback\n2\tbot_tts_sink\n").encode()
        sources = "".encode()

        mock_sinks = self._make_pactl_mock(stdout=sinks)
        mock_sources = self._make_pactl_mock(stdout=sources)

        bridge = PulseAudioBridge()
        with patch(
            "hermes_agent_ts3.audio_bridge.asyncio.create_subprocess_exec",
            side_effect=[mock_sinks, mock_sources],
        ):
            assert await bridge.verify() is False

    @pytest.mark.asyncio
    async def test_verify_sinks_failed_returns_false(self):
        mock_fail = self._make_pactl_mock(stdout="".encode(), returncode=1)

        bridge = PulseAudioBridge()
        with patch(
            "hermes_agent_ts3.audio_bridge.asyncio.create_subprocess_exec",
            side_effect=[mock_fail],
        ):
            assert await bridge.verify() is False


class TestDeviceNameConstruction:
    def test_monitor_name_from_sink(self):
        bridge = PulseAudioBridge(sink_name="foo")
        info = PulseAudioDeviceInfo(
            sink_name=bridge._sink_name,
            monitor_name=f"{bridge._sink_name}.monitor",
            source_name=bridge._source_name,
            tts_sink_name=bridge._tts_sink_name,
        )
        assert info.monitor_name == "foo.monitor"

    def test_custom_names_propagate(self):
        bridge = PulseAudioBridge(sink_name="play", source_name="cap", tts_sink_name="tts")
        assert bridge._sink_name == "play"
        assert bridge._source_name == "cap"
        assert bridge._tts_sink_name == "tts"
