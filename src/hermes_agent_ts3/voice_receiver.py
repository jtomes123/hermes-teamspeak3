import asyncio
import logging
import math
import threading
from enum import Enum, auto
from typing import Awaitable, Callable, Optional

from hermes_agent_ts3.voice_constants import (
    CHANNELS,
    DTYPE,
    FRAME_SAMPLES,
    SAMPLE_RATE,
)

logger = logging.getLogger(__name__)


class VADState(Enum):
    SILENCE = auto()
    SPEECH = auto()


def _process_vad_frame(
    state: VADState,
    is_speech: bool,
    frames_speech: int,
    frames_silence: int,
    speech_frames_threshold: int,
    silence_frames_threshold: int,
) -> tuple[VADState, int, int, bool]:
    if state == VADState.SILENCE:
        if is_speech:
            frames_speech += 1
            frames_silence = 0
            if frames_speech >= speech_frames_threshold:
                return VADState.SPEECH, frames_speech, 0, False
        else:
            frames_speech = 0
        return state, frames_speech, frames_silence, False
    elif state == VADState.SPEECH:
        if is_speech:
            frames_silence = 0
        else:
            frames_silence += 1
            if frames_silence >= silence_frames_threshold:
                return VADState.SILENCE, 0, 0, True
        return state, frames_speech, frames_silence, False
    return state, frames_speech, frames_silence, False


class TS3VoiceReceiver:
    def __init__(
        self,
        device_name: str = "ts3_playback.monitor",
        sample_rate: int = SAMPLE_RATE,
        channels: int = CHANNELS,
        dtype: str = DTYPE,
        frame_samples: int = FRAME_SAMPLES,
        silence_duration: float = 1.5,
        min_speech_duration: float = 0.5,
        energy_threshold: float = 500.0,
        event_loop: Optional[asyncio.AbstractEventLoop] = None,
    ):
        self._device_name = device_name
        self._sample_rate = sample_rate
        self._channels = channels
        self._dtype = dtype
        self._frame_samples = frame_samples
        self._silence_duration = silence_duration
        self._min_speech_duration = min_speech_duration
        self._energy_threshold = energy_threshold
        self._event_loop = event_loop

        self._stream = None
        self._thread: Optional[threading.Thread] = None
        self._running: bool = False
        self._paused = threading.Event()
        self._paused.set()
        self._callback: Optional[Callable[[bytes], Awaitable[None]]] = None
        self._callback_lock = threading.Lock()

        self._silence_frames_threshold: int = 0
        self._speech_frames_threshold: int = 0

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def is_paused(self) -> bool:
        return not self._paused.is_set()

    def on_utterance(self, callback: Callable[[bytes], Awaitable[None]]):
        with self._callback_lock:
            self._callback = callback

    def pause(self):
        self._paused.clear()
        logger.debug("Voice capture paused")

    def resume(self):
        self._paused.set()
        logger.debug("Voice capture resumed")

    def start(self):
        try:
            import sounddevice as sd
        except ImportError:
            raise RuntimeError("sounddevice is not installed")

        if self._running:
            return

        frame_duration_s = self._frame_samples / self._sample_rate
        self._silence_frames_threshold = int(self._silence_duration / frame_duration_s)
        self._speech_frames_threshold = int(self._min_speech_duration / frame_duration_s)

        self._running = True
        self._stream = sd.InputStream(
            device=self._device_name,
            samplerate=self._sample_rate,
            channels=self._channels,
            dtype=self._dtype,
            blocksize=self._frame_samples,
            callback=None,
        )
        self._stream.start()

        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()
        logger.debug("Voice capture started on %s", self._device_name)

    def stop(self):
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None
        logger.debug("Voice capture stopped")

    def _rms(self, chunk: bytes) -> float:
        if self._dtype != "int16":
            raise ValueError(f"Unsupported dtype '{self._dtype}': _rms only supports int16")

        import array

        samples = array.array("h", chunk)
        if len(samples) == 0:
            return 0.0
        sum_sq = sum(s * s for s in samples)
        return math.sqrt(sum_sq / len(samples))

    def _capture_loop(self):
        try:
            state = VADState.SILENCE
            frames_silence = 0
            frames_speech = 0
            utterance_buffer: list[bytes] = []

            while self._running:
                try:
                    data, overflowed = self._stream.read(self._frame_samples)
                except Exception:
                    if not self._running:
                        break
                    raise

                if not self._paused.is_set():
                    continue

                if overflowed:
                    logger.warning("Audio input overflow")

                energy = self._rms(bytes(data))
                is_speech = energy > self._energy_threshold

                prev_state = state
                state, frames_speech, frames_silence, should_finalize = _process_vad_frame(
                    state, is_speech, frames_speech, frames_silence,
                    self._speech_frames_threshold, self._silence_frames_threshold,
                )

                if prev_state == VADState.SILENCE and state == VADState.SPEECH:
                    logger.debug("VAD: speech start (energy=%.1f)", energy)

                if is_speech or prev_state == VADState.SPEECH:
                    utterance_buffer.append(bytes(data))

                if should_finalize:
                    logger.debug("VAD: speech end (%.1fs silence)", self._silence_duration)
                    self._finalize_utterance(utterance_buffer)
                    utterance_buffer = []

        except Exception as e:
            if self._running:
                logger.error("Capture loop error: %s", e)

    def _finalize_utterance(self, buffer: list[bytes]):
        if not buffer:
            return
        pcm = b"".join(buffer)
        try:
            wav = self._pcm_to_wav(pcm)
        except Exception as e:
            logger.error("PCM to WAV conversion failed: %s", e)
            return

        with self._callback_lock:
            cb = self._callback

        if cb is not None:
            loop = self._event_loop or asyncio.get_event_loop()
            asyncio.run_coroutine_threadsafe(cb(wav), loop)

    def _pcm_to_wav(self, pcm: bytes) -> bytes:
        import struct
        import wave
        import io

        buf = io.BytesIO()
        wf = wave.open(buf, "wb")
        wf.setnchannels(self._channels)
        wf.setsampwidth(2)
        wf.setframerate(self._sample_rate)
        wf.writeframes(pcm)
        wf.close()
        return buf.getvalue()
