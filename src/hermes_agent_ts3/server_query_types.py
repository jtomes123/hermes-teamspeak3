from dataclasses import dataclass


class TS3QueryError(Exception):
    def __init__(self, code: int, msg: str, extra: dict | None = None):
        self.code = code
        self.msg = msg
        self.extra = extra or {}
        super().__init__(f"TS3 error {code}: {msg}")


class TS3ConnectionError(Exception):
    pass


class TS3AuthError(TS3QueryError):
    pass


# -- Event dataclasses --

@dataclass(slots=True)
class TS3TextMessageEvent:
    targetmode: int
    msg: str
    invokerid: int
    invokername: str
    invokeruid: str

    @classmethod
    def from_notify(cls, data: dict[str, str]) -> "TS3TextMessageEvent":
        return cls(
            targetmode=int(data.get("targetmode", 0)),
            msg=data.get("msg", ""),
            invokerid=int(data.get("invokerid", 0)),
            invokername=data.get("invokername", ""),
            invokeruid=data.get("invokeruid", ""),
        )


@dataclass(slots=True)
class TS3ClientEnterViewEvent:
    ctid: int
    clid: int
    client_nickname: str
    raw: dict[str, str]

    @classmethod
    def from_notify(cls, data: dict[str, str]) -> "TS3ClientEnterViewEvent":
        ctid = data.get("ctid", "0")
        return cls(
            ctid=int(ctid),
            clid=int(data.get("clid", "0")),
            client_nickname=data.get("client_nickname", ""),
            raw=data,
        )


@dataclass(slots=True)
class TS3ClientLeftViewEvent:
    ctid: int
    clid: int
    raw: dict[str, str]

    @classmethod
    def from_notify(cls, data: dict[str, str]) -> "TS3ClientLeftViewEvent":
        return cls(
            ctid=int(data.get("ctid", "0")),
            clid=int(data.get("clid", "0")),
            raw=data,
        )


@dataclass(slots=True)
class TS3ClientMovedEvent:
    ctid: int
    clid: int
    client_nickname: str
    raw: dict[str, str]

    @classmethod
    def from_notify(cls, data: dict[str, str]) -> "TS3ClientMovedEvent":
        return cls(
            ctid=int(data.get("ctid", "0")),
            clid=int(data.get("clid", "0")),
            client_nickname=data.get("client_nickname", ""),
            raw=data,
        )


TS3Event = (
    TS3TextMessageEvent
    | TS3ClientEnterViewEvent
    | TS3ClientLeftViewEvent
    | TS3ClientMovedEvent
)


# -- Response type --

TS3Response = list[dict[str, str]]


# -- Parsing helpers --

_ESCAPE_TABLE: dict[str, str] = {
    "\\": "\\",
    "/": "/",
    "s": " ",
    "p": "|",
    "a": "\a",
    "b": "\b",
    "f": "\f",
    "n": "\n",
    "r": "\r",
    "t": "\t",
    "v": "\v",
}

_REVERSE_ESCAPE_TABLE: dict[str, str] = {v: k for k, v in _ESCAPE_TABLE.items()}


def _unescape_ts3_value(val: str) -> str:
    parts: list[str] = []
    i = 0
    while i < len(val):
        if val[i] == "\\" and i + 1 < len(val):
            code = val[i + 1]
            parts.append(_ESCAPE_TABLE.get(code, val[i : i + 2]))
            i += 2
        else:
            parts.append(val[i])
            i += 1
    return "".join(parts)


def _escape_ts3_value(val: str) -> str:
    parts: list[str] = []
    for ch in val:
        if ch in _REVERSE_ESCAPE_TABLE:
            parts.append("\\" + _REVERSE_ESCAPE_TABLE[ch])
        else:
            parts.append(ch)
    return "".join(parts)


def _parse_ts3_line(line: str) -> dict[str, str]:
    parts = line.split(" ")
    result: dict[str, str] = {}
    for part in parts:
        if "=" not in part:
            continue
        key, _, value = part.partition("=")
        result[key] = _unescape_ts3_value(value)
    return result


def _parse_ts3_response(lines: list[str]) -> TS3Response:
    if not lines:
        return []
    joined = "".join(lines)
    entries = joined.split("|")
    return [_parse_ts3_line(entry) for entry in entries if entry.strip()]


def _parse_error_line(line: str) -> tuple[int, str, dict | None]:
    data = _parse_ts3_line(line)
    code = int(data.get("id", "0"))
    msg = data.get("msg", "")
    extra = {k: v for k, v in data.items() if k not in ("id", "msg")}
    return code, msg, (extra if extra else None)


def _encode_command(name: str, params: dict[str, str]) -> str:
    parts = [name]
    for key, value in params.items():
        escaped = _escape_ts3_value(str(value))
        parts.append(f"{key}={escaped}")
    return " ".join(parts)


_NOTIFY_EVENT_MAP: dict[str, type] = {
    "notifytextmessage": TS3TextMessageEvent,
    "notifycliententerview": TS3ClientEnterViewEvent,
    "notifyclientleftview": TS3ClientLeftViewEvent,
    "notifyclientmoved": TS3ClientMovedEvent,
}


def _parse_event(data: dict[str, str], notify_type: str) -> TS3Event | None:
    event_cls = _NOTIFY_EVENT_MAP.get(notify_type)
    if event_cls is None:
        return None
    return event_cls.from_notify(data)
