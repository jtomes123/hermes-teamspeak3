from dataclasses import dataclass, field
import os


def _parse_comma_list(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _parse_int_env(value: str | None, default: int) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def _parse_float_env(value: str | None, default: float) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def _parse_bool_env(value: str | None) -> bool:
    if value is None:
        return False
    return value.lower() in ("1", "true", "yes")


@dataclass
class TS3Config:
    server_host: str = ""
    serverquery_port: int = 10011
    serverquery_user: str = ""
    serverquery_pass: str = field(default="", repr=False)
    voice_port: int = 9987
    home_channel: str = ""
    allowed_users: list[str] = field(default_factory=list)
    allowed_channels: list[str] = field(default_factory=list)
    allow_all_users: bool = False
    identity_file: str = "ts3_identity"
    nickname: str = "Hermes"
    server_password: str = field(default="", repr=False)
    client_download_url: str = ""
    client_download_checksum: str = ""
    client_data_dir: str = "ts3_client_data"
    pulse_sink: str = "ts3_playback"
    pulse_source: str = "bot_tts"
    pulse_server: str = ""
    xvfb_display: str = ":99"
    command_prefix: str = "!"
    mention_gating: bool = False
    reconnect_base: float = 1.0
    reconnect_max: float = 60.0

    @classmethod
    def from_env(cls) -> "TS3Config":
        return cls(
            server_host=os.environ.get("TS3_SERVER_HOST", ""),
            serverquery_port=_parse_int_env(
                os.environ.get("TS3_SERVERQUERY_PORT"), 10011
            ),
            serverquery_user=os.environ.get("TS3_SERVERQUERY_USER", ""),
            serverquery_pass=os.environ.get("TS3_SERVERQUERY_PASS", ""),
            voice_port=_parse_int_env(
                os.environ.get("TS3_VOICE_PORT"), 9987
            ),
            home_channel=os.environ.get("TS3_HOME_CHANNEL", ""),
            allowed_users=_parse_comma_list(
                os.environ.get("TS3_ALLOWED_USERS")
            ),
            allowed_channels=_parse_comma_list(
                os.environ.get("TS3_ALLOWED_CHANNELS")
            ),
            allow_all_users=_parse_bool_env(
                os.environ.get("TS3_ALLOW_ALL_USERS")
            ),
            identity_file=os.environ.get(
                "TS3_IDENTITY_FILE", "ts3_identity"
            ),
            nickname=os.environ.get("TS3_NICKNAME", "Hermes"),
            server_password=os.environ.get("TS3_SERVER_PASSWORD", ""),
            client_download_url=os.environ.get("TS3_CLIENT_DOWNLOAD_URL", ""),
            client_download_checksum=os.environ.get(
                "TS3_CLIENT_DOWNLOAD_CHECKSUM", ""
            ),
            client_data_dir=os.environ.get(
                "TS3_CLIENT_DATA_DIR", "ts3_client_data"
            ),
            pulse_sink=os.environ.get("TS3_PULSE_SINK", "ts3_playback"),
            pulse_source=os.environ.get("TS3_PULSE_SOURCE", "bot_tts"),
            pulse_server=os.environ.get("TS3_PULSE_SERVER", ""),
            xvfb_display=os.environ.get("TS3_XVFB_DISPLAY", ":99"),
            command_prefix=os.environ.get("TS3_COMMAND_PREFIX", "!"),
            mention_gating=_parse_bool_env(
                os.environ.get("TS3_MENTION_GATING")
            ),
            reconnect_base=_parse_float_env(
                os.environ.get("TS3_RECONNECT_BASE"), 1.0
            ),
            reconnect_max=_parse_float_env(
                os.environ.get("TS3_RECONNECT_MAX"), 60.0
            ),
        )
