import asyncio
import threading
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hermes_agent_ts3.voice_receiver import TS3VoiceReceiver, VADState


class TestVoiceConstants:
    def test_frame_bytes_calculation(self):
        from hermes_agent_ts3.voice_constants import (
            CHANNELS,
            DTYPE,
            FRAME_BYTES,
            FRAME_SAMPLES,
            SAMPLE_RATE,
        )

        assert SAMPLE_RATE == 48000
        assert CHANNELS == 2
        assert DTYPE == "int16"
        assert FRAME_SAMPLES == 960
        assert FRAME_BYTES == 960 * 2 * 2


class TestTS3VoiceReceiverInit:
    def test_default_values(self):
        r = TS3VoiceReceiver()
        assert r._device_name == "ts3_playback.monitor"
        assert r._sample_rate == 48000
        assert r._channels == 2
        assert r._dtype == "int16"
        assert r._frame_samples == 960
        assert r._silence_duration == 1.5
        assert r._min_speech_duration == 0.5
        assert r._energy_threshold == 500.0
        assert r.is_running is False
        assert r.is_paused is False

    def test_custom_values(self):
        r = TS3VoiceReceiver(
            device_name="custom_monitor",
            sample_rate=16000,
            channels=1,
            dtype="float32",
            frame_samples=512,
            silence_duration=2.0,
            min_speech_duration=0.3,
            energy_threshold=300.0,
        )
        assert r._device_name == "custom_monitor"
        assert r._sample_rate == 16000
        assert r._channels == 1
        assert r._dtype == "float32"
        assert r._frame_samples == 512
        assert r._silence_duration == 2.0
        assert r._min_speech_duration == 0.3
        assert r._energy_threshold == 300.0


class TestTS3VoiceReceiverPauseResume:
    def test_pause(self):
        r = TS3VoiceReceiver()
        r.pause()
        assert r.is_paused is True

    def test_resume(self):
        r = TS3VoiceReceiver()
        r.pause()
        r.resume()
        assert r.is_paused is False

    def test_default_not_paused(self):
        r = TS3VoiceReceiver()
        assert r.is_paused is False


class TestTS3VoiceReceiverCallback:
    def test_set_callback(self):
        r = TS3VoiceReceiver()
        called = []

        async def cb(wav):
            called.append(wav)

        r.on_utterance(cb)
        assert r._callback is cb

    def test_replace_callback(self):
        r = TS3VoiceReceiver()
        cb1 = AsyncMock()
        cb2 = AsyncMock()
        r.on_utterance(cb1)
        r.on_utterance(cb2)
        assert r._callback is cb2


class TestTS3VoiceReceiverRMS:
    def test_rms_silence(self):
        import array

        r = TS3VoiceReceiver()
        chunk = array.array("h", [0] * 960).tobytes()
        energy = r._rms(chunk)
        assert energy == 0.0

    def test_rms_signal(self):
        import array

        r = TS3VoiceReceiver()
        chunk = array.array("h", [1000] * 960).tobytes()
        energy = r._rms(chunk)
        assert energy == 1000.0

    def test_rms_empty(self):
        r = TS3VoiceReceiver()
        energy = r._rms(b"")
        assert energy == 0.0

    def test_rms_unsupported_dtype(self):
        r = TS3VoiceReceiver(dtype="float32")
        with pytest.raises(ValueError, match="Unsupported dtype"):
            r._rms(b"\x00" * 10)


class TestTS3VoiceReceiverPCMToWAV:
    def test_pcm_to_wav_produces_valid_wav(self):
        import array
        import wave
        import io

        r = TS3VoiceReceiver()
        samples = array.array("h", [0] * 960 * 2).tobytes()
        wav = r._pcm_to_wav(samples)
        wf = wave.open(io.BytesIO(wav), "rb")
        assert wf.getnchannels() == 2
        assert wf.getsampwidth() == 2
        assert wf.getframerate() == 48000
        assert wf.getnframes() > 0


class TestTS3VoiceReceiverLifecycle:
    @pytest.mark.asyncio
    async def test_start_stop(self):
        mock_sd = MagicMock()
        mock_stream = MagicMock()

        with patch.dict("sys.modules", {"sounddevice": mock_sd}):
            mock_sd.InputStream.return_value = mock_stream

            r = TS3VoiceReceiver()
            r.start()
            assert r.is_running is True
            mock_sd.InputStream.assert_called_once_with(
                device="ts3_playback.monitor",
                samplerate=48000,
                channels=2,
                dtype="int16",
                blocksize=960,
                callback=None,
            )
            mock_stream.start.assert_called_once()

            r.stop()
            assert r.is_running is False
            mock_stream.stop.assert_called_once()
            mock_stream.close.assert_called_once()

    def test_start_when_already_running(self):
        mock_sd = MagicMock()
        mock_stream = MagicMock()

        with patch.dict("sys.modules", {"sounddevice": mock_sd}):
            mock_sd.InputStream.return_value = mock_stream
            r = TS3VoiceReceiver()
            r.start()
            r.start()
            assert mock_sd.InputStream.call_count == 1

    def test_start_missing_dependency(self):
        r = TS3VoiceReceiver()
        with patch.dict("sys.modules", {"sounddevice": None}):
            with pytest.raises(RuntimeError, match="sounddevice"):
                r.start()


class TestVADStateMachine:
    def _make_data(self, energy):
        import array

        return bytes(array.array("h", [int(energy)] * 960 * 2))

    def test_silence_to_speech(self):
        from hermes_agent_ts3.voice_receiver import _process_vad_frame, VADState

        r = TS3VoiceReceiver(
            min_speech_duration=0.5,
            energy_threshold=500.0,
            frame_samples=480,
        )
        r._silence_frames_threshold = 75
        r._speech_frames_threshold = 50

        state = VADState.SILENCE
        frames_speech = 0
        frames_silence = 0

        for _ in range(50):
            energy = r._rms(self._make_data(600.0))
            is_speech = energy > r._energy_threshold
            state, frames_speech, frames_silence, finalized = _process_vad_frame(
                state, is_speech, frames_speech, frames_silence,
                r._speech_frames_threshold, r._silence_frames_threshold,
            )

        assert state == VADState.SPEECH
        assert frames_speech == 50

    def test_speech_to_silence_to_utterance(self):
        from hermes_agent_ts3.voice_receiver import _process_vad_frame, VADState

        r = TS3VoiceReceiver(
            silence_duration=1.0,
            energy_threshold=500.0,
            frame_samples=480,
        )
        r._silence_frames_threshold = 100
        r._speech_frames_threshold = 50

        state = VADState.SPEECH
        frames_speech = 50
        frames_silence = 0

        for _ in range(100):
            energy = r._rms(self._make_data(100.0))
            is_speech = energy > r._energy_threshold
            state, frames_speech, frames_silence, finalized = _process_vad_frame(
                state, is_speech, frames_speech, frames_silence,
                r._speech_frames_threshold, r._silence_frames_threshold,
            )

        assert frames_silence == 0
        assert state == VADState.SILENCE

    def test_below_threshold_stays_silent(self):
        from hermes_agent_ts3.voice_receiver import _process_vad_frame, VADState

        r = TS3VoiceReceiver(
            min_speech_duration=0.5,
            energy_threshold=500.0,
            frame_samples=480,
        )
        r._speech_frames_threshold = 50

        state = VADState.SILENCE
        frames_speech = 0
        frames_silence = 0

        for _ in range(50):
            energy = r._rms(self._make_data(100.0))
            is_speech = energy > r._energy_threshold
            state, frames_speech, frames_silence, finalized = _process_vad_frame(
                state, is_speech, frames_speech, frames_silence,
                r._speech_frames_threshold, r._silence_frames_threshold,
            )

        assert frames_speech == 0
        assert state == VADState.SILENCE


class TestTS3VoiceReceiverPauseSkipsVAD:
    def _make_data(self, energy):
        import array

        return bytes(array.array("h", [int(energy)] * 960 * 2))

    def test_paused_skips_vad(self):
        mock_sd = MagicMock()
        mock_stream = MagicMock()
        mock_stream.read.return_value = (bytearray(self._make_data(600.0)), False)

        with patch.dict("sys.modules", {"sounddevice": mock_sd}):
            mock_sd.InputStream.return_value = mock_stream
            r = TS3VoiceReceiver(
                min_speech_duration=0.5,
                energy_threshold=500.0,
                frame_samples=480,
            )
            r.start()
            r.pause()
            assert r.is_paused is True
