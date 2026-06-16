import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hermes_agent_ts3.voice_player import TS3VoicePlayer


class TestTS3VoicePlayerInit:
    def test_default_values(self):
        p = TS3VoicePlayer()
        assert p._device_name == "bot_tts_sink"
        assert p._sample_rate == 48000
        assert p._channels == 2
        assert p._dtype == "int16"
        assert p.is_playing is False

    def test_custom_values(self):
        p = TS3VoicePlayer(
            device_name="custom_sink",
            sample_rate=44100,
            channels=1,
            dtype="float32",
        )
        assert p._device_name == "custom_sink"
        assert p._sample_rate == 44100
        assert p._channels == 1
        assert p._dtype == "float32"


class TestTS3VoicePlayerLifecycle:
    def test_start_stop(self):
        mock_sd = MagicMock()
        mock_stream = MagicMock()

        with patch.dict("sys.modules", {"sounddevice": mock_sd}):
            mock_sd.OutputStream.return_value = mock_stream

            p = TS3VoicePlayer()
            p.start()
            mock_sd.OutputStream.assert_called_once_with(
                device="bot_tts_sink",
                samplerate=48000,
                channels=2,
                dtype="int16",
            )
            mock_stream.start.assert_called_once()

            p.stop()
            mock_stream.stop.assert_called_once()
            mock_stream.close.assert_called_once()

    def test_start_missing_dependency(self):
        p = TS3VoicePlayer()
        with patch.dict("sys.modules", {"sounddevice": None}):
            with pytest.raises(RuntimeError, match="sounddevice"):
                p.start()


class TestTS3VoicePlayerPlayPCM:
    @pytest.mark.asyncio
    async def test_play_pcm_writes_in_chunks(self):
        mock_sd = MagicMock()
        mock_stream = MagicMock()

        with patch.dict("sys.modules", {"sounddevice": mock_sd}):
            mock_sd.OutputStream.return_value = mock_stream

            p = TS3VoicePlayer()
            p.start()

            pcm = b"\x00" * (3840 * 3)
            await p.play_pcm(pcm)

            assert mock_stream.write.call_count == 3

    @pytest.mark.asyncio
    async def test_play_pcm_sets_is_playing(self):
        mock_sd = MagicMock()
        mock_stream = MagicMock()

        with patch.dict("sys.modules", {"sounddevice": mock_sd}):
            mock_sd.OutputStream.return_value = mock_stream

            p = TS3VoicePlayer()
            p.start()

            pcm = b"\x00" * 3840
            await p.play_pcm(pcm)

            assert p.is_playing is False

    @pytest.mark.asyncio
    async def test_play_pcm_requires_started(self):
        p = TS3VoicePlayer()
        with pytest.raises(RuntimeError, match="not started"):
            await p.play_pcm(b"test")

    @pytest.mark.asyncio
    async def test_play_cancellation(self):
        mock_sd = MagicMock()
        mock_stream = MagicMock()

        with patch.dict("sys.modules", {"sounddevice": mock_sd}):
            mock_sd.OutputStream.return_value = mock_stream

            p = TS3VoicePlayer()
            p.start()

            pcm = b"\x00" * (3840 * 100)

            async def cancel_soon():
                await asyncio.sleep(0.01)
                p.stop_playback()

            async def do_play():
                await p.play_pcm(pcm)

            task = asyncio.create_task(do_play())
            await cancel_soon()
            await task

            assert p.is_playing is False


class TestTS3VoicePlayerStopPlayback:
    @pytest.mark.asyncio
    async def test_stop_playback_noop_when_not_playing(self):
        mock_sd = MagicMock()
        mock_stream = MagicMock()

        with patch.dict("sys.modules", {"sounddevice": mock_sd}):
            mock_sd.OutputStream.return_value = mock_stream
            p = TS3VoicePlayer()
            p.start()
            p.stop_playback()
            assert p._cancel_event is None


class TestTS3VoicePlayerPlayFile:
    @pytest.mark.asyncio
    async def test_play_file_decode_and_write(self):
        mock_sd = MagicMock()
        mock_stream = MagicMock()

        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        mock_pcm = [b"\x00" * 3840, b"\x01" * 3840, b""]

        async def mock_read(size):
            return mock_pcm.pop(0) if mock_pcm else b""

        mock_proc.stdout.read = mock_read
        mock_proc.wait = AsyncMock()

        with patch.dict("sys.modules", {"sounddevice": mock_sd}):
            mock_sd.OutputStream.return_value = mock_stream
            with patch(
                "hermes_agent_ts3.voice_player.asyncio.create_subprocess_exec",
                return_value=mock_proc,
            ):
                p = TS3VoicePlayer()
                p.start()
                await p.play_file("test.wav")

                assert mock_stream.write.call_count == 2
                assert p.is_playing is False

    @pytest.mark.asyncio
    async def test_play_file_requires_started(self):
        p = TS3VoicePlayer()
        with pytest.raises(RuntimeError, match="not started"):
            await p.play_file("test.wav")

    @pytest.mark.asyncio
    async def test_play_file_cancellation(self):
        mock_sd = MagicMock()
        mock_stream = MagicMock()

        mock_proc = AsyncMock()
        mock_proc.returncode = 0

        async def mock_read(size):
            await asyncio.sleep(0.1)
            return b"\x00" * 3840

        mock_proc.stdout.read = mock_read
        mock_proc.wait = AsyncMock()
        mock_proc.terminate = MagicMock()

        with patch.dict("sys.modules", {"sounddevice": mock_sd}):
            mock_sd.OutputStream.return_value = mock_stream
            with patch(
                "hermes_agent_ts3.voice_player.asyncio.create_subprocess_exec",
                return_value=mock_proc,
            ):
                p = TS3VoicePlayer()
                p.start()

                async def cancel_soon():
                    await asyncio.sleep(0.01)
                    p.stop_playback()

                async def do_play():
                    await p.play_file("test.wav")

                task = asyncio.create_task(do_play())
                await cancel_soon()
                await task

                mock_proc.terminate.assert_called_once()
                assert p.is_playing is False


class TestIsPlaying:
    def test_is_playing_initially_false(self):
        p = TS3VoicePlayer()
        assert p.is_playing is False

    @pytest.mark.asyncio
    async def test_is_playing_during_playback(self):
        mock_sd = MagicMock()
        mock_stream = MagicMock()

        with patch.dict("sys.modules", {"sounddevice": mock_sd}):
            mock_sd.OutputStream.return_value = mock_stream

            p = TS3VoicePlayer()
            p.start()

            playing_states = []

            def sync_write(chunk):
                playing_states.append(p.is_playing)

            mock_stream.write = sync_write

            await p.play_pcm(b"\x00" * (3840 * 10))

            assert True in playing_states
