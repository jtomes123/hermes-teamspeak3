import asyncio
import logging
import os
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class PulseAudioDeviceInfo:
    sink_name: str
    monitor_name: str
    source_name: str
    tts_sink_name: str
    module_ids: list[int] = field(default_factory=list)


class PulseAudioBridge:
    def __init__(
        self,
        pulse_server: str = "",
        sink_name: str = "ts3_playback",
        source_name: str = "bot_tts",
        tts_sink_name: str = "bot_tts_sink",
    ):
        self._pulse_server = pulse_server
        self._sink_name = sink_name
        self._source_name = source_name
        self._tts_sink_name = tts_sink_name
        self._module_ids: list[int] = []
        self._device_info: Optional[PulseAudioDeviceInfo] = None

    def _build_env(self) -> dict:
        env = os.environ.copy()
        if self._pulse_server:
            env["PULSE_SERVER"] = self._pulse_server
        return env

    async def _pactl(self, *args: str) -> int:
        env = self._build_env()
        proc = await asyncio.create_subprocess_exec(
            "pactl",
            *args,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            logger.error("pactl %s failed: %s", " ".join(args), stderr.decode())
            raise RuntimeError(f"pactl {' '.join(args)} failed: {stderr.decode()}")
        output = stdout.decode().strip()
        try:
            return int(output)
        except (ValueError, TypeError):
            logger.warning("Could not parse module ID from pactl output: %s", output)
            return -1

    async def _run_pactl(self, *args: str) -> str:
        env = self._build_env()
        proc = await asyncio.create_subprocess_exec(
            "pactl",
            *args,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            logger.error("pactl %s failed: %s", " ".join(args), stderr.decode())
            return ""
        return stdout.decode()

    async def _find_existing_modules(self) -> Optional[PulseAudioDeviceInfo]:
        env = self._build_env()
        try:
            sinks_proc = await asyncio.create_subprocess_exec(
                "pactl", "list", "short", "sinks",
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            sources_proc = await asyncio.create_subprocess_exec(
                "pactl", "list", "short", "sources",
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            sinks_stdout, _ = await asyncio.wait_for(sinks_proc.communicate(), timeout=10)
            sources_stdout, _ = await asyncio.wait_for(sources_proc.communicate(), timeout=10)
            sinks = sinks_stdout.decode()
            sources = sources_stdout.decode()
            sink_names = {parts[1] for line in sinks.splitlines()
                          if (parts := line.split('\t')) and len(parts) >= 2}
            source_names = {parts[1] for line in sources.splitlines()
                            if (parts := line.split('\t')) and len(parts) >= 2}
        except (asyncio.TimeoutError, FileNotFoundError) as e:
            logger.warning("pactl unavailable: %s", e)
            return None

        has_playback = self._sink_name in sink_names
        has_tts_sink = self._tts_sink_name in sink_names
        has_tts_source = self._source_name in source_names

        if has_playback and has_tts_sink and has_tts_source:
            return PulseAudioDeviceInfo(
                sink_name=self._sink_name,
                monitor_name=f"{self._sink_name}.monitor",
                source_name=self._source_name,
                tts_sink_name=self._tts_sink_name,
            )
        return None

    async def start(self) -> PulseAudioDeviceInfo:
        existing = await self._find_existing_modules()
        if existing is not None:
            logger.debug("Audio devices already exist, reusing")
            self._device_info = existing
            return existing

        logger.debug("Creating PulseAudio virtual devices")
        self._module_ids = []

        try:
            mod_id = await self._pactl(
                "load-module", "module-null-sink",
                f"sink_name={self._sink_name}",
                "sink_properties=device.description=TS3_Playback",
            )
            if mod_id >= 0:
                self._module_ids.append(mod_id)
                logger.debug("Created sink %s (module %d)", self._sink_name, mod_id)

            mod_id = await self._pactl(
                "load-module", "module-null-sink",
                f"sink_name={self._tts_sink_name}",
                "sink_properties=device.description=Bot_TTS_Sink",
            )
            if mod_id >= 0:
                self._module_ids.append(mod_id)
                logger.debug("Created sink %s (module %d)", self._tts_sink_name, mod_id)

            mod_id = await self._pactl(
                "load-module", "module-remap-source",
                f"source_name={self._source_name}",
                f"master={self._tts_sink_name}.monitor",
                "source_properties=device.description=Bot_TTS",
            )
            if mod_id >= 0:
                self._module_ids.append(mod_id)
                logger.debug("Created source %s (module %d)", self._source_name, mod_id)
        except Exception:
            await self.stop()
            raise

        info = PulseAudioDeviceInfo(
            sink_name=self._sink_name,
            monitor_name=f"{self._sink_name}.monitor",
            source_name=self._source_name,
            tts_sink_name=self._tts_sink_name,
            module_ids=list(self._module_ids),
        )
        self._device_info = info
        return info

    async def stop(self) -> None:
        for mod_id in reversed(self._module_ids):
            try:
                await self._pactl("unload-module", str(mod_id))
                logger.debug("Unloaded module %d", mod_id)
            except Exception as e:
                logger.warning("Failed to unload module %d: %s", mod_id, e)
        self._module_ids.clear()
        self._device_info = None

    async def verify(self) -> bool:
        output = await self._run_pactl("list", "short", "sinks")
        if not output:
            return False
        sources = await self._run_pactl("list", "short", "sources")
        sink_names = {parts[1] for line in output.splitlines()
                      if (parts := line.split('\t')) and len(parts) >= 2}
        source_names = {parts[1] for line in sources.splitlines()
                        if (parts := line.split('\t')) and len(parts) >= 2}
        has_playback = self._sink_name in sink_names
        has_tts = self._tts_sink_name in sink_names
        has_source = self._source_name in source_names
        return has_playback and has_tts and has_source
