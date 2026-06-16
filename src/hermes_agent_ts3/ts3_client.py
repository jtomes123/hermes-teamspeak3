import asyncio
import logging
import os
import signal
import sqlite3
import subprocess
import time
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class TS3ClientConfig:
    binary_path: str = ""
    data_dir: str = "ts3_client_data"
    identity_file: str = "ts3_identity"
    display: str = ":99"
    server_host: str = ""
    voice_port: int = 9987
    server_password: str = ""
    nickname: str = "Hermes"
    playback_device: str = "ts3_playback"
    capture_device: str = "bot_tts"
    reconnect_base: float = 1.0
    reconnect_max: float = 60.0


class TS3ClientManager:
    def __init__(self, config: TS3ClientConfig):
        self._config = config
        self._process: Optional[asyncio.subprocess.Process] = None
        self._monitor_task: Optional[asyncio.Task] = None
        self._stdout_task: Optional[asyncio.Task] = None
        self._stderr_task: Optional[asyncio.Task] = None
        self._reconnect_task: Optional[asyncio.Task] = None
        self._shutting_down: bool = False
        self._data_dir = Path(config.data_dir)

    @property
    def running(self) -> bool:
        return self._process is not None and self._process.returncode is None

    @property
    def pid(self) -> Optional[int]:
        if self._process is not None:
            return self._process.pid
        return None

    async def _ensure_identity(self) -> None:
        self._data_dir.mkdir(parents=True, exist_ok=True)
        identity_path = self._data_dir / self._config.identity_file
        if identity_path.exists():
            logger.debug("Identity file exists at %s", identity_path)
            return

        logger.debug("Generating TS3 identity (first run)...")
        binary = self._config.binary_path
        if not binary:
            binary = "ts3client_linux_amd64"
        identity_gen = await asyncio.create_subprocess_exec(
            binary,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
            env={
                **os.environ,
                "DISPLAY": self._config.display,
            },
            cwd=str(self._data_dir),
        )

        timeout = 120
        start_time = time.monotonic()
        while time.monotonic() - start_time < timeout:
            if identity_gen.returncode is not None:
                break
            if identity_path.exists():
                break
            await asyncio.sleep(1)

        if identity_gen.returncode is None:
            try:
                identity_gen.terminate()
                await asyncio.wait_for(identity_gen.wait(), timeout=5)
            except asyncio.TimeoutError:
                identity_gen.kill()
                await identity_gen.wait()

        if not identity_path.exists():
            raise RuntimeError(
                f"Identity was not generated at {identity_path}. "
                f"Make sure the TS3 client binary is correct: {binary}"
            )

        logger.debug("Identity generated at %s", identity_path)

    def _ensure_table(self, conn: sqlite3.Connection, table: str) -> None:
        conn.execute(
            f"CREATE TABLE IF NOT EXISTS {table} (key TEXT PRIMARY KEY, value TEXT)"
        )
        conn.commit()

    async def _configure_settings_db(self) -> None:
        db_path = self._data_dir / "settings.db"
        self._data_dir.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_path))

        self._ensure_table(conn, "Bookmarks")
        self._ensure_table(conn, "Playback")
        self._ensure_table(conn, "Capture")

        conn.execute(
            "INSERT OR REPLACE INTO Playback (key, value) VALUES (?, ?)",
            ("default", self._config.playback_device),
        )
        conn.execute(
            "INSERT OR REPLACE INTO Capture (key, value) VALUES (?, ?)",
            ("default", self._config.capture_device),
        )

        conn_str = (
            f"ts3server://{self._config.server_host}?"
            f"port={self._config.voice_port}"
            f"&nickname={urllib.parse.quote(self._config.nickname, safe='')}"
        )
        if self._config.server_password:
            conn_str += f"&password={urllib.parse.quote(self._config.server_password, safe='')}"

        conn.execute(
            "INSERT OR REPLACE INTO Bookmarks (key, value) VALUES (?, ?)",
            ("default", conn_str),
        )
        conn.commit()
        conn.close()
        logger.debug("settings.db configured at %s", db_path)

    def _build_env(self) -> dict[str, str]:
        env = os.environ.copy()
        env["DISPLAY"] = self._config.display
        return env

    async def _capture_stdout(self) -> None:
        if self._process is None or self._process.stdout is None:
            return
        try:
            while True:
                line = await self._process.stdout.readline()
                if not line:
                    break
                logger.debug("TS3 stdout: %s", line.decode(errors="replace").rstrip())
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.warning("Error reading TS3 stdout: %s", e)

    async def _capture_stderr(self) -> None:
        if self._process is None or self._process.stderr is None:
            return
        try:
            while True:
                line = await self._process.stderr.readline()
                if not line:
                    break
                logger.debug("TS3 stderr: %s", line.decode(errors="replace").rstrip())
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.warning("Error reading TS3 stderr: %s", e)

    async def _launch_client(self) -> None:
        binary = self._config.binary_path
        if not binary:
            binary = "ts3client_linux_amd64"

        logger.debug("Launching TS3 client: %s", binary)
        self._process = await asyncio.create_subprocess_exec(
            binary,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=self._build_env(),
            cwd=str(self._data_dir),
            preexec_fn=os.setsid if hasattr(os, "setsid") else None,
        )
        logger.debug("TS3 client started (PID %d)", self._process.pid)

        self._stdout_task = asyncio.create_task(self._capture_stdout())
        self._stderr_task = asyncio.create_task(self._capture_stderr())

    def _kill_process(self) -> None:
        if self._process is None or self._process.returncode is not None:
            return
        pid = self._process.pid
        logger.info("Sending SIGTERM to TS3 client (PID %d)", pid)
        try:
            os.killpg(os.getpgid(pid), signal.SIGTERM)
        except (ProcessLookupError, OSError):
            try:
                self._process.terminate()
            except ProcessLookupError:
                pass

    async def _reconnect(self) -> None:
        if self._shutting_down:
            return
        delay = self._config.reconnect_base
        max_delay = self._config.reconnect_max
        attempt = 0
        while not self._shutting_down:
            attempt += 1
            logger.debug(
                "Reconnect attempt %d — waiting %.1fs", attempt, delay
            )
            await asyncio.sleep(delay)
            if self._shutting_down:
                return
            try:
                await self._ensure_identity()
                await self._configure_settings_db()
                await self._launch_client()
                self._monitor_task = asyncio.create_task(self._monitor_loop())
                logger.info("Reconnect successful")
                return
            except Exception as e:
                logger.error("Reconnect attempt %d failed: %s", attempt, e)
                delay = min(delay * 2, max_delay)

    async def _monitor_loop(self) -> None:
        if self._process is None:
            return
        try:
            exit_code = await self._process.wait()
            if self._shutting_down:
                return
            logger.info("TS3 client exited with code %d", exit_code)
        except asyncio.CancelledError:
            return
        finally:
            self._process = None
        if not self._shutting_down:
            self._reconnect_task = asyncio.create_task(self._reconnect())

    async def start(self) -> None:
        self._shutting_down = False
        await self._ensure_identity()
        await self._configure_settings_db()
        await self._launch_client()
        self._monitor_task = asyncio.create_task(self._monitor_loop())

    async def stop(self) -> None:
        self._shutting_down = True
        if self._reconnect_task:
            self._reconnect_task.cancel()
            self._reconnect_task = None

        for task in [self._monitor_task, self._stdout_task, self._stderr_task]:
            if task:
                task.cancel()

        self._kill_process()

        if self._process is not None:
            try:
                await asyncio.wait_for(self._process.wait(), timeout=5)
            except asyncio.TimeoutError:
                logger.warning("Sending SIGKILL to TS3 client (PID %d)", self._process.pid)
                try:
                    os.killpg(os.getpgid(self._process.pid), signal.SIGKILL)
                except (ProcessLookupError, OSError):
                    self._process.kill()
                await self._process.wait()

        self._process = None

    async def is_healthy(self) -> bool:
        if self._process is None:
            return False
        return self._process.returncode is None
