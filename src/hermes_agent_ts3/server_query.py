import asyncio
import logging
from collections.abc import AsyncIterator

from .server_query_types import (
    TS3AuthError,
    TS3ConnectionError,
    TS3Event,
    TS3QueryError,
    TS3Response,
    _encode_command,
    _escape_ts3_value,
    _parse_error_line,
    _parse_event,
    _parse_ts3_line,
    _parse_ts3_response,
)

logger = logging.getLogger(__name__)

DEFAULT_PORT = 10011
DEFAULT_KEEPALIVE_INTERVAL = 120.0
DEFAULT_RECONNECT_BASE = 1.0
DEFAULT_RECONNECT_MAX = 60.0
DEFAULT_COMMAND_TIMEOUT = 10.0


class TS3ServerQuery:
    def __init__(
        self,
        host: str,
        port: int = DEFAULT_PORT,
        username: str = "serveradmin",
        password: str = "",
        virtual_server_id: int = 1,
        *,
        keepalive_interval: float = DEFAULT_KEEPALIVE_INTERVAL,
        reconnect_base: float = DEFAULT_RECONNECT_BASE,
        reconnect_max: float = DEFAULT_RECONNECT_MAX,
        reconnect_enabled: bool = True,
        command_timeout: float = DEFAULT_COMMAND_TIMEOUT,
    ):
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._virtual_server_id = virtual_server_id
        self._keepalive_interval = keepalive_interval
        self._reconnect_base = reconnect_base
        self._reconnect_max = reconnect_max
        self._reconnect_enabled = reconnect_enabled
        self._command_timeout = command_timeout

        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._lock = asyncio.Lock()
        self._event_queue: asyncio.Queue[TS3Event] = asyncio.Queue()
        self._response_future: asyncio.Future[tuple[list[str], int, str, dict | None]] | None = None
        self._response_lines: list[str] = []
        self._connected = asyncio.Event()
        self._shutting_down = asyncio.Event()
        self._keepalive_task: asyncio.Task[None] | None = None
        self._reader_task: asyncio.Task[None] | None = None

    async def __aenter__(self) -> "TS3ServerQuery":
        await self.connect()
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.disconnect()

    # -- Lifecycle --

    async def connect(self) -> None:
        self._shutting_down.clear()
        await self._handshake()

    async def disconnect(self) -> None:
        self._shutting_down.set()
        self._connected.clear()
        if self._keepalive_task:
            self._keepalive_task.cancel()
            self._keepalive_task = None
        if self._reader_task:
            self._reader_task.cancel()
            self._reader_task = None
        self._cancel_pending()
        if self._writer:
            self._writer.close()
            await self._writer.wait_closed()
            self._writer = None
            self._reader = None

    async def _handshake(self) -> None:
        try:
            self._reader, self._writer = await asyncio.open_connection(
                self._host, self._port
            )
        except OSError as exc:
            raise TS3ConnectionError(
                f"Failed to connect to {self._host}:{self._port}"
            ) from exc

        await self._read_banner()
        await self._login()
        await self._select_server()
        await self._register_events()

        self._connected.set()
        self._keepalive_task = asyncio.create_task(self._keepalive_loop())
        self._reader_task = asyncio.create_task(self._reader_loop())

    async def _read_banner(self) -> None:
        reader = self._reader
        if reader is None:
            raise TS3ConnectionError("Not connected")
        line = await reader.readline()
        if not line:
            raise TS3ConnectionError("No banner received from server")
        banner = line.decode("utf-8", errors="replace").strip()
        logger.debug("TS3 banner: %s", banner)
        if banner.startswith("error "):
            code, msg, _ = _parse_error_line(banner)
            if code == 520:
                raise TS3AuthError(code, msg)
            raise TS3QueryError(code, msg)

    async def _login(self) -> None:
        await self._raw_execute(
            f"login {self._username} {self._password}"
        )

    async def _select_server(self) -> None:
        await self._raw_execute(f"use sid={self._virtual_server_id}")

    async def _register_events(self) -> None:
        events = "textserver|textchannel|textprivate|server"
        await self._raw_execute(f"servernotifyregister event={events}")

    # -- Raw command execution (no locking, for internal use) --

    async def _raw_execute(self, command: str) -> TS3Response:
        writer = self._writer
        if writer is None:
            raise TS3ConnectionError("Not connected")
        self._response_future = asyncio.get_event_loop().create_future()
        self._response_lines = []

        writer.write(command.encode("utf-8") + b"\n")
        await writer.drain()

        try:
            data, code, msg, extra = await asyncio.wait_for(
                self._response_future, timeout=self._command_timeout
            )
        except asyncio.TimeoutError:
            self._response_future = None
            raise TS3ConnectionError(
                f"Command timed out after {self._command_timeout}s: {command}"
            )
        self._response_future = None

        if code != 0:
            if code == 520:
                raise TS3AuthError(code, msg, extra)
            raise TS3QueryError(code, msg, extra)

        return _parse_ts3_response(data)

    def _cancel_pending(self) -> None:
        if self._response_future and not self._response_future.done():
            self._response_future.set_exception(
                TS3ConnectionError("Connection lost")
            )
            self._response_future = None

    # -- Reader loop --

    async def _reader_loop(self) -> None:
        while not self._shutting_down.is_set():
            try:
                reader = self._reader
                if reader is None:
                    await asyncio.sleep(0.5)
                    continue
                line = await reader.readline()
            except (OSError, asyncio.IncompleteReadError):
                if not self._shutting_down.is_set():
                    logger.warning("Reader connection lost, triggering reconnect")
                    await self._reconnect()
                continue

            if not line:
                if not self._shutting_down.is_set():
                    logger.warning("Server closed connection, triggering reconnect")
                    await self._reconnect()
                continue

            decoded = line.decode("utf-8", errors="replace").rstrip("\n\r")
            if not decoded:
                continue

            if decoded.startswith("notify"):
                self._dispatch_notify(decoded)
            elif decoded.startswith("error "):
                self._dispatch_error(decoded)
            elif self._response_future is not None:
                self._response_lines.append(decoded)

    def _dispatch_notify(self, line: str) -> None:
        space_idx = line.find(" ")
        if space_idx == -1:
            return
        notify_type = line[:space_idx]
        body = line[space_idx + 1:]
        data = _parse_ts3_line(body)
        event = _parse_event(data, notify_type)
        if event is not None:
            self._event_queue.put_nowait(event)

    def _dispatch_error(self, line: str) -> None:
        if self._response_future is not None:
            code, msg, extra = _parse_error_line(line)
            lines = list(self._response_lines)
            self._response_lines.clear()
            self._response_future.set_result((lines, code, msg, extra))

    # -- Reconnection --

    async def _reconnect(self) -> None:
        self._connected.clear()
        self._cancel_pending()

        if self._keepalive_task:
            self._keepalive_task.cancel()
            self._keepalive_task = None
        if self._reader_task:
            self._reader_task.cancel()
            self._reader_task = None

        if not self._reconnect_enabled:
            self._shutting_down.set()
            return

        if self._writer:
            self._writer.close()
            self._writer = None
            self._reader = None

        backoff = self._reconnect_base
        while not self._shutting_down.is_set():
            try:
                await self._handshake()
                logger.info("Reconnected to TS3 ServerQuery")
                return
            except (TS3ConnectionError, TS3QueryError, OSError) as exc:
                logger.warning(
                    "Reconnect attempt failed: %s. Retrying in %.1fs",
                    exc,
                    backoff,
                )
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, self._reconnect_max)

    # -- Keepalive --

    async def _keepalive_loop(self) -> None:
        while not self._shutting_down.is_set():
            await asyncio.sleep(self._keepalive_interval)
            if self._connected.is_set() and not self._shutting_down.is_set():
                try:
                    await self.execute("whoami")
                except (TS3ConnectionError, TS3QueryError, OSError):
                    logger.warning("Keepalive failed, marking disconnected")
                    self._connected.clear()
                    if self._reconnect_enabled:
                        asyncio.create_task(
                            self._reconnect()
                        )

    # -- Public API --

    async def execute(self, command: str) -> TS3Response:
        async with self._lock:
            if not self._connected.is_set():
                raise TS3ConnectionError("Not connected to TS3 ServerQuery")
            return await self._raw_execute(command)

    async def client_list(self) -> list[dict[str, str]]:
        return await self.execute("clientlist -uid -nick -voice")

    async def client_info(self, client_id: int) -> dict[str, str]:
        result = await self.execute(f"clientinfo clid={client_id}")
        if not result:
            raise TS3QueryError(0, f"No client info for clid={client_id}")
        return result[0]

    async def client_move(self, client_id: int, channel_id: int) -> None:
        await self.execute(f"clientmove clid={client_id} cid={channel_id}")

    async def client_get_id_by_nickname(self, nickname: str) -> int | None:
        result = await self.execute(f"clientfind pattern={nickname}")
        if not result:
            return None
        for client in result:
            if client.get("client_nickname", "").lower() == nickname.lower():
                return int(client["clid"])
        return None

    async def channel_list(self) -> list[dict[str, str]]:
        return await self.execute("channellist")

    async def channel_info(self, channel_id: int) -> dict[str, str]:
        result = await self.execute(f"channelinfo cid={channel_id}")
        if not result:
            raise TS3QueryError(0, f"No channel info for cid={channel_id}")
        return result[0]

    async def channel_find(self, name: str) -> list[dict[str, str]]:
        return await self.execute(f"channelfind pattern={name}")

    async def send_text_message(
        self, target_mode: int, target_id: int, message: str
    ) -> None:
        escaped = _escape_ts3_value(message)
        await self.execute(
            f"sendtextmessage targetmode={target_mode} "
            f"target={target_id} msg={escaped}"
        )

    async def events(self) -> AsyncIterator[TS3Event]:
        while not self._shutting_down.is_set():
            try:
                event = await self._event_queue.get()
                yield event
            except asyncio.CancelledError:
                break

    @property
    def is_connected(self) -> bool:
        return self._connected.is_set()
