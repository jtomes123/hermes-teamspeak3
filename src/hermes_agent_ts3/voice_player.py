import asyncio
import logging
import threading
from typing import Optional

from hermes_agent_ts3.voice_constants import (
    CHANNELS,
    DTYPE,
    SAMPLE_RATE,
)

logger = logging.getLogger(__name__)


class TS3VoicePlayer:
    def __init__(
        self,
        device_name: str = "bot_tts_sink",
        sample_rate: int = SAMPLE_RATE,
        channels: int = CHANNELS,
        dtype: str = DTYPE,
    ):
        self._device_name = device_name
        self._sample_rate = sample_rate
        self._channels = channels
        self._dtype = dtype

        self._stream = None
        self._playing: bool = False
        self._cancel_event: Optional[asyncio.Event] = None
        self._play_lock = asyncio.Lock()
        self._idle = threading.Event()
        self._idle.set()

    @property
    def is_playing(self) -> bool:
        return self._playing

    def start(self):
        try:
            import sounddevice as sd
        except ImportError:
            raise RuntimeError("sounddevice is not installed")

        self._stream = sd.OutputStream(
            device=self._device_name,
            samplerate=self._sample_rate,
            channels=self._channels,
            dtype=self._dtype,
        )
        self._stream.start()
        logger.debug("Voice player started on %s", self._device_name)

    def stop(self):
        self.stop_playback()
        self._idle.wait(timeout=5.0)
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        logger.debug("Voice player stopped")

    def stop_playback(self):
        if self._cancel_event is not None:
            self._cancel_event.set()

    async def play_pcm(self, pcm: bytes):
        if self._stream is None:
            raise RuntimeError("Player not started")

        self._idle.clear()
        try:
            async with self._play_lock:
                self._playing = True
                self._cancel_event = asyncio.Event()

                chunk_size = 960 * self._channels * 2
                i = 0
                while i < len(pcm):
                    if self._cancel_event.is_set():
                        break
                    chunk = pcm[i:i + chunk_size]
                    await asyncio.to_thread(self._stream.write, chunk)
                    i += chunk_size

                self._cancel_event = None
                self._playing = False
        finally:
            self._idle.set()

    async def play_file(self, file_path: str):
        if self._stream is None:
            raise RuntimeError("Player not started")

        self._idle.clear()
        try:
            async with self._play_lock:
                self._playing = True
                self._cancel_event = asyncio.Event()

                try:
                    proc = await asyncio.create_subprocess_exec(
                        "ffmpeg",
                        "-i", file_path,
                        "-f", "s16le",
                        "-acodec", "pcm_s16le",
                        "-ar", str(self._sample_rate),
                        "-ac", str(self._channels),
                        "pipe:1",
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.DEVNULL,
                    )

                    chunk_size = 960 * self._channels * 2
                    while True:
                        if self._cancel_event.is_set():
                            proc.terminate()
                            break
                        chunk = await proc.stdout.read(chunk_size)
                        if not chunk:
                            break
                        await asyncio.to_thread(self._stream.write, chunk)

                    await proc.wait()
                except Exception as e:
                    logger.error("Playback error: %s", e)
                finally:
                    self._cancel_event = None
                    self._playing = False
        finally:
            self._idle.set()
