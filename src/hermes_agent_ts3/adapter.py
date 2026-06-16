import asyncio
import hashlib
import logging
import os
import tarfile
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path
from typing import Optional

from gateway.config import Platform, PlatformConfig
from gateway.platforms.base import (
    BasePlatformAdapter,
    MessageEvent,
    MessageType,
    SendResult,
    SessionSource,
)
from tools.transcription_tools import transcribe_audio
from tools.voice_mode import is_whisper_hallucination

from .audio_bridge import PulseAudioBridge
from .commands import CommandHandler, CommandContext, CommandResult
from .config import TS3Config
from .server_query import TS3ServerQuery
from .server_query_types import TS3ClientMovedEvent, TS3TextMessageEvent, TS3ConnectionError, TS3QueryError
from .ts3_client import TS3ClientConfig, TS3ClientManager
from .voice_player import TS3VoicePlayer
from .voice_receiver import TS3VoiceReceiver

logger = logging.getLogger(__name__)

IDLE_TIMEOUT = 300.0
IDLE_CHECK_INTERVAL = 60.0
CLIENT_FIND_TIMEOUT = 30.0


class TeamSpeakAdapter(BasePlatformAdapter):
    def __init__(self, config: PlatformConfig, platform: Platform):
        super().__init__(config, platform)
        self._ts3_config = TS3Config.from_env()
        self._sq: TS3ServerQuery | None = None
        self._client: TS3ClientManager | None = None
        self._audio_bridge: PulseAudioBridge | None = None
        self._voice_receiver: TS3VoiceReceiver | None = None
        self._voice_player: TS3VoicePlayer | None = None
        self._home_channel_id: int | None = None
        self._current_channel_id: int | None = None
        self._my_client_id: int | None = None
        self._idle_since: float = time.monotonic()
        self._cmd_handler: CommandHandler = CommandHandler(self._ts3_config)
        self._start_time: float = 0.0
        self._idle_task: asyncio.Task | None = None
        self._event_task: asyncio.Task | None = None
        self._voice_listen_active = asyncio.Event()
        self._message_origins: dict[str, int] = {}
        self._voice_lock = asyncio.Lock()
        self._running = False

    # -- Lifecycle --

    async def connect(self) -> bool:
        logger.info("Starting TeamSpeak adapter...")

        device_info = await self._start_audio_bridge()

        binary_path = await self._ensure_client_binary()

        client_cfg = TS3ClientConfig(
            binary_path=binary_path,
            data_dir=self._ts3_config.client_data_dir,
            identity_file=self._ts3_config.identity_file,
            display=self._ts3_config.xvfb_display,
            server_host=self._ts3_config.server_host,
            voice_port=self._ts3_config.voice_port,
            server_password=self._ts3_config.server_password,
            nickname=self._ts3_config.nickname,
            playback_device=device_info.sink_name,
            capture_device=device_info.source_name,
            reconnect_base=self._ts3_config.reconnect_base,
            reconnect_max=self._ts3_config.reconnect_max,
        )

        await self._start_client(client_cfg)

        await self._start_server_query()

        self._my_client_id = await self._find_my_client_id()

        self._home_channel_id = await self._resolve_home_channel()
        await self._sq.client_move(self._my_client_id, self._home_channel_id)

        await self._start_voice_player()
        await self._start_voice_receiver()

        self._running = True
        self._event_task = asyncio.create_task(self._event_loop())
        self._idle_task = asyncio.create_task(self._idle_watcher())

        self._idle_since = time.monotonic()
        self._start_time = time.monotonic()
        logger.info("TeamSpeak adapter connected (client_id=%d, home_channel=%d)",
                     self._my_client_id, self._home_channel_id)
        return True

    async def disconnect(self) -> None:
        logger.info("Disconnecting TeamSpeak adapter...")
        self._running = False

        self._voice_listen_active.clear()

        for task in [self._event_task, self._idle_task]:
            if task:
                task.cancel()

        if self._voice_receiver:
            self._voice_receiver.stop()

        if self._voice_player:
            self._voice_player.stop()

        for task in [self._event_task, self._idle_task]:
            if task:
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        if self._sq:
            await self._sq.disconnect()
            self._sq = None

        if self._client:
            await self._client.stop()
            self._client = None

        if self._audio_bridge:
            await self._audio_bridge.stop()
            self._audio_bridge = None

        self._my_client_id = None
        self._home_channel_id = None
        self._current_channel_id = None

        logger.info("TeamSpeak adapter disconnected")

    # -- Configuration property --

    @property
    def is_connected(self) -> bool:
        return self._my_client_id is not None

    # -- Internal helpers --

    async def _start_audio_bridge(self):
        cfg = self._ts3_config
        self._audio_bridge = PulseAudioBridge(
            pulse_server=cfg.pulse_server,
            sink_name=cfg.pulse_sink,
            source_name=cfg.pulse_source,
            tts_sink_name="bot_tts_sink",
        )
        return await self._audio_bridge.start()

    async def _ensure_client_binary(self) -> str:
        data_dir = Path(self._ts3_config.client_data_dir)
        data_dir.mkdir(parents=True, exist_ok=True)

        binary_name = "ts3client_linux_amd64"
        binary_path = data_dir / binary_name

        if binary_path.exists():
            logger.debug("TS3 client binary found at %s", binary_path)
            return str(binary_path)

        url = self._ts3_config.client_download_url
        if not url:
            logger.debug("No download URL configured, using system binary")
            return binary_name

        return await self._download_client(url, data_dir, binary_name)

    async def _download_client(self, url: str, data_dir: Path, binary_name: str) -> str:
        logger.info("Downloading TS3 client from %s", url)

        tmp_path = None
        try:
            tmp_fd, tmp_path = tempfile.mkstemp(suffix=".download")
            os.close(tmp_fd)

            await asyncio.to_thread(urllib.request.urlretrieve, url, tmp_path)

            expected = self._ts3_config.client_download_checksum
            if expected:
                actual = await asyncio.to_thread(self._hash_file, tmp_path)
                if actual != expected:
                    raise RuntimeError(
                        f"Checksum mismatch: expected {expected}, got {actual}"
                    )

            await asyncio.to_thread(self._extract_archive, tmp_path, data_dir)

            binary_path = data_dir / binary_name
            if not binary_path.exists():
                for candidate in data_dir.rglob(binary_name):
                    binary_path = candidate
                    break

            if not binary_path.exists():
                raise RuntimeError(
                    f"TS3 client binary not found after extraction in {data_dir}"
                )

            os.chmod(str(binary_path), 0o755)
            logger.info("TS3 client binary ready at %s", binary_path)
            return str(binary_path)
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)

    @staticmethod
    def _hash_file(path: str) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()

    @staticmethod
    def _extract_archive(src: str, dest: Path) -> None:
        dest.mkdir(parents=True, exist_ok=True)
        if src.endswith((".tar.gz", ".tgz")):
            with tarfile.open(src, "r:gz") as tf:
                tf.extractall(dest)
        elif src.endswith(".zip"):
            with zipfile.ZipFile(src, "r") as zf:
                zf.extractall(dest)
        else:
            import shutil

            binary = dest / "ts3client_linux_amd64"
            shutil.copy(src, str(binary))

    async def _start_client(self, cfg: TS3ClientConfig) -> None:
        self._client = TS3ClientManager(cfg)
        await self._client.start()
        logger.debug("TS3 client started")

    async def _start_server_query(self) -> None:
        cfg = self._ts3_config
        self._sq = TS3ServerQuery(
            host=cfg.server_host,
            port=cfg.serverquery_port,
            username=cfg.serverquery_user,
            password=cfg.serverquery_pass,
            reconnect_base=cfg.reconnect_base,
            reconnect_max=cfg.reconnect_max,
        )
        await self._sq.connect()
        logger.debug("ServerQuery connected")

    async def _find_my_client_id(self) -> int:
        nickname = self._ts3_config.nickname
        deadline = time.monotonic() + CLIENT_FIND_TIMEOUT

        while time.monotonic() < deadline:
            try:
                clients = await self._sq.client_list()
                for client in clients:
                    if client.get("client_nickname", "").lower() == nickname.lower():
                        return int(client["clid"])
            except (TS3ConnectionError, TS3QueryError, asyncio.TimeoutError, OSError):
                pass
            await asyncio.sleep(1.0)

        raise RuntimeError(
            f"Client with nickname '{nickname}' not found "
            f"within {CLIENT_FIND_TIMEOUT}s"
        )

    async def _resolve_home_channel(self) -> int:
        name = self._ts3_config.home_channel
        if not name:
            channels = await self._sq.channel_list()
            if not channels:
                raise RuntimeError("No channels available and TS3_HOME_CHANNEL not set")
            return int(channels[0]["cid"])

        results = await self._sq.channel_find(name)
        for ch in results:
            if ch.get("channel_name", "").lower() == name.lower():
                return int(ch["cid"])

        raise RuntimeError(f"Home channel '{name}' not found")

    async def _start_voice_player(self) -> None:
        self._voice_player = TS3VoicePlayer(
            device_name="bot_tts_sink",
        )
        try:
            await asyncio.to_thread(self._voice_player.start)
        except Exception as exc:
            self._list_audio_devices()
            raise RuntimeError(
                f"Failed to start voice player on 'bot_tts_sink': {exc}. "
                "Is PulseAudio running and setup_audio.sh executed?"
            ) from exc
        logger.info("Voice player started on bot_tts_sink")

    async def _start_voice_receiver(self) -> None:
        device = f"{self._ts3_config.pulse_sink}.monitor"
        self._voice_receiver = TS3VoiceReceiver(
            device_name=device,
            event_loop=asyncio.get_running_loop(),
        )
        self._voice_receiver.on_utterance(self._on_utterance)
        try:
            await asyncio.to_thread(self._voice_receiver.start)
        except Exception as exc:
            self._list_audio_devices()
            raise RuntimeError(
                f"Failed to start voice receiver on '{device}': {exc}. "
                "Is PulseAudio running and setup_audio.sh executed?"
            ) from exc
        self._voice_receiver.pause()
        logger.info("Voice receiver started on %s (paused)", device)

    @staticmethod
    def _list_audio_devices() -> None:
        try:
            import sounddevice as sd
            devices = sd.query_devices()
            logger.error("Available audio devices:")
            for i, d in enumerate(devices):
                logger.error("  [%d] %s (in=%d, out=%d, hostapi=%s)",
                             i, d["name"], d["max_input_channels"],
                             d["max_output_channels"], d.get("hostapi", "?"))
        except Exception:
            pass

    # -- Event loop --

    async def _event_loop(self) -> None:
        logger.debug("Event loop started")
        while self._running:
            try:
                async for event in self._sq.events():
                    if isinstance(event, TS3TextMessageEvent):
                        await self._handle_text_message(event)
                    elif isinstance(event, TS3ClientMovedEvent):
                        await self._handle_client_moved(event)
            except asyncio.CancelledError:
                return
            except (TS3ConnectionError, StopAsyncIteration):
                if not self._running:
                    return
                logger.warning("ServerQuery events lost, waiting for reconnect...")
                await asyncio.sleep(2)
            except Exception as exc:
                if not self._running:
                    return
                logger.error("Event loop error: %s", exc)
                await asyncio.sleep(2)

    async def _handle_text_message(self, event: TS3TextMessageEvent) -> None:
        if event.invokerid == self._my_client_id:
            return

        text = event.msg.strip()

        parsed = self._cmd_handler.parse_command(text)
        if parsed is not None:
            if not self._cmd_handler.is_allowed_user(event.invokername):
                return
            cmd_name, cmd_args = parsed
            ctx = await self._build_command_context(event)
            result = self._cmd_handler.handle(cmd_name, cmd_args, ctx)
            await self._execute_command_result(result, event)
            return

        if self._ts3_config.mention_gating:
            return

        if not self._is_allowed_user(event.invokername):
            return

        chat_id = str(event.invokerid) if event.targetmode == 1 else str(self._current_channel_id or self._home_channel_id or 0)
        if event.targetmode == 1:
            self._message_origins[f"client:{chat_id}"] = 1
        self._reset_idle()

        source = SessionSource(
            platform=str(self.platform),
            chat_id=chat_id,
            user_id=event.invokeruid,
            user_name=event.invokername,
        )

        msg_event = MessageEvent(
            source=source,
            chat_id=chat_id,
            content=event.msg,
            type=MessageType.TEXT,
            metadata={"invokeruid": event.invokeruid},
        )

        await self.handle_message(msg_event)

    async def _handle_client_moved(self, event: TS3ClientMovedEvent) -> None:
        if event.clid == self._my_client_id:
            self._current_channel_id = event.ctid
            logger.debug("Moved to channel %d", event.ctid)

    async def _build_command_context(self, event: TS3TextMessageEvent) -> CommandContext:
        chat_id = str(event.invokerid) if event.targetmode == 1 else str(self._current_channel_id or self._home_channel_id or 0)

        invoker_channel_id = None
        invoker_channel_name = "unknown"
        if self._sq is not None and self._sq.is_connected:
            try:
                client_data = await self._sq.client_info(event.invokerid)
                invoker_channel_id = int(client_data.get("cid", 0))
                channel_data = await self._sq.channel_info(invoker_channel_id)
                invoker_channel_name = channel_data.get("channel_name", "unknown")
            except Exception:
                pass

        current_channel_name = "unknown"
        if self._sq is not None and self._sq.is_connected and self._current_channel_id is not None:
            try:
                channel_data = await self._sq.channel_info(self._current_channel_id)
                current_channel_name = channel_data.get("channel_name", "unknown")
            except Exception:
                pass

        uptime = time.monotonic() - self._start_time

        return CommandContext(
            invoker_name=event.invokername,
            invoker_id=event.invokerid,
            invoker_uid=event.invokeruid,
            invoker_channel_id=invoker_channel_id,
            invoker_channel_name=invoker_channel_name,
            current_channel_id=self._current_channel_id,
            current_channel_name=current_channel_name,
            home_channel_id=self._home_channel_id,
            voice_mode=self._cmd_handler.voice_mode,
            uptime_seconds=uptime,
            chat_id=chat_id,
        )

    async def _execute_command_result(self, result: CommandResult, event: TS3TextMessageEvent) -> None:
        if result.reply and self._sq is not None and self._sq.is_connected:
            target_mode = event.targetmode if event.targetmode == 1 else 2
            if target_mode == 1:
                target_id = event.invokerid
            else:
                target_id = self._current_channel_id or self._home_channel_id or 0

            try:
                await self._sq.send_text_message(
                    target_mode=target_mode,
                    target_id=target_id,
                    message=result.reply,
                )
            except Exception as exc:
                logger.error("Failed to send command reply: %s", exc)

        if result.move_to_channel_id is not None:
            await self.join_voice_channel(result.move_to_channel_id)
            self._reset_idle()

        if result.move_to_home:
            await self.leave_voice_channel()

        if result.set_voice_mode is not None:
            self._cmd_handler.voice_mode = result.set_voice_mode
            if result.set_voice_mode == "on":
                self._start_voice_listen()
            else:
                self._stop_voice_listen()

    # -- Auth --

    def _is_allowed_user(self, nickname: str) -> bool:
        if self._ts3_config.allow_all_users:
            return True

        allowed = self._ts3_config.allowed_users
        if not allowed:
            return True

        return nickname.lower() in [u.lower() for u in allowed]

    # -- Idle management --

    def _reset_idle(self) -> None:
        self._idle_since = time.monotonic()

    async def _idle_watcher(self) -> None:
        try:
            while True:
                await asyncio.sleep(IDLE_CHECK_INTERVAL)
                elapsed = time.monotonic() - self._idle_since
                if elapsed > IDLE_TIMEOUT and self._current_channel_id != self._home_channel_id:
                    if self._home_channel_id is not None and self._my_client_id is not None:
                        logger.debug("Idle timeout (%.0fs), returning to home channel", elapsed)
                        await self.leave_voice_channel()
        except asyncio.CancelledError:
            pass

    # -- Voice --

    async def join_voice_channel(self, channel_id: int) -> bool:
        async with self._voice_lock:
            if self._sq is None or self._my_client_id is None:
                return False

            try:
                await self._sq.client_move(self._my_client_id, channel_id)
            except Exception as exc:
                logger.error("Failed to join voice channel %d: %s", channel_id, exc)
                return False

            self._current_channel_id = channel_id
            self._reset_idle()
            self._start_voice_listen()
            logger.info("Joined voice channel %d", channel_id)
            return True

    async def leave_voice_channel(self) -> None:
        self._stop_voice_listen()

        async with self._voice_lock:
            if self._sq is None or self._my_client_id is None or self._home_channel_id is None:
                return

            try:
                await self._sq.client_move(self._my_client_id, self._home_channel_id)
                self._current_channel_id = self._home_channel_id
                logger.debug("Returned to home channel")
            except Exception as exc:
                logger.error("Failed to return to home channel: %s", exc)

    def _start_voice_listen(self) -> None:
        if self._voice_receiver is None:
            return
        self._voice_receiver.resume()
        self._voice_listen_active.set()

    def _stop_voice_listen(self) -> None:
        if self._voice_receiver is None:
            return
        self._voice_listen_active.clear()
        self._voice_receiver.pause()

    async def _on_utterance(self, wav_bytes: bytes) -> None:
        if not self._voice_listen_active.is_set():
            return

        try:
            text = await asyncio.to_thread(transcribe_audio, wav_bytes)
        except Exception as exc:
            logger.error("Transcription failed: %s", exc)
            return

        if not text or not text.strip():
            return

        try:
            if is_whisper_hallucination(text):
                logger.debug("Filtered hallucination: %s", text)
                return
        except Exception:
            pass

        chat_id = str(self._current_channel_id or self._home_channel_id or 0)

        source = SessionSource(
            platform=str(self.platform),
            chat_id=chat_id,
            user_id="voice",
            user_name="voice",
        )

        msg_event = MessageEvent(
            source=source,
            chat_id=chat_id,
            content=text.strip(),
            type=MessageType.VOICE,
            metadata={"utterance": True},
        )

        await self.handle_message(msg_event)

    # -- TTS / Voice Messages --

    async def play_tts(self, chat_id: str, audio_path: str, **kwargs) -> SendResult:
        if self._voice_player is None:
            logger.error("Voice player not initialized")
            return SendResult(success=False, message_id="")

        was_active = (self._voice_receiver is not None
                     and not self._voice_receiver.is_paused)
        if was_active:
            self._voice_receiver.pause()

        try:
            await self._voice_player.play_file(audio_path)
            return SendResult(success=True, message_id="tts")
        except Exception as exc:
            logger.error("TTS playback failed: %s", exc)
            return SendResult(success=False, message_id="")
        finally:
            if was_active:
                self._voice_receiver.resume()

    async def send_voice(self, chat_id: str, audio_path: str, caption: str = "",
                         reply_to: str | None = None, metadata: dict | None = None,
                         **kwargs) -> SendResult:
        return await self.play_tts(chat_id, audio_path, **kwargs)

    # -- Send / Receive --

    async def send(self, chat_id: str, content: str, reply_to: str | None = None,
                   metadata: dict | None = None) -> SendResult:
        if self._sq is None:
            return SendResult(success=False, message_id="")

        try:
            target_id = int(chat_id)
        except (ValueError, TypeError):
            target_id = self._home_channel_id or 0

        await self._sq.send_text_message(
            target_mode=self._message_origins.get(f"client:{chat_id}", 2),
            target_id=target_id,
            message=content,
        )
        self._reset_idle()
        return SendResult(success=True, message_id=chat_id)

    async def get_chat_info(self, chat_id: str) -> dict:
        if self._sq is None:
            return {}
        try:
            return await self._sq.channel_info(int(chat_id))
        except Exception:
            return {}
