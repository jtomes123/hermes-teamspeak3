import time
from dataclasses import dataclass

from .config import TS3Config


VOICE_HELP = (
    "!voice on — activate voice transcription\n"
    "!voice off — deactivate voice transcription\n"
    "!voice tts — TTS-only mode"
)

COMMANDS_HELP = (
    "!summon — move bot to your channel\n"
    "!leave — send bot back to home channel\n"
    "!voice <on|off|tts> — change voice mode\n"
    "!status — show current status\n"
    "!help — show this help"
)


@dataclass
class CommandContext:
    invoker_name: str
    invoker_id: int
    invoker_uid: str
    invoker_channel_id: int | None
    invoker_channel_name: str
    current_channel_id: int | None
    current_channel_name: str
    home_channel_id: int | None
    voice_mode: str
    uptime_seconds: float
    chat_id: str


@dataclass
class CommandResult:
    reply: str | None = None
    move_to_channel_id: int | None = None
    move_to_home: bool = False
    set_voice_mode: str | None = None


class CommandHandler:
    def __init__(self, config: TS3Config):
        self._config = config
        self._start_time = time.monotonic()
        self._voice_mode = "on"

    @property
    def start_time(self) -> float:
        return self._start_time

    @property
    def voice_mode(self) -> str:
        return self._voice_mode

    @voice_mode.setter
    def voice_mode(self, value: str) -> None:
        self._voice_mode = value

    def parse_command(self, text: str) -> tuple[str, str] | None:
        text = text.strip()
        if not text.startswith(self._config.command_prefix):
            return None
        content = text[len(self._config.command_prefix):].strip()
        if not content:
            return None
        parts = content.split(None, 1)
        name = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""
        return name, args

    def is_allowed_user(self, nickname: str) -> bool:
        if self._config.allow_all_users:
            return True
        allowed = self._config.allowed_users
        if not allowed:
            return True
        return nickname.lower() in [u.lower() for u in allowed]

    def is_allowed_channel(self, channel_name: str) -> bool:
        allowed = self._config.allowed_channels
        if not allowed:
            return True
        return channel_name.lower() in [c.lower() for c in allowed]

    def handle(self, command: str, args: str, ctx: CommandContext) -> CommandResult:
        handlers = {
            "summon": self._handle_summon,
            "leave": self._handle_leave,
            "voice": self._handle_voice,
            "status": self._handle_status,
            "help": self._handle_help,
        }
        handler = handlers.get(command)
        if handler is None:
            return CommandResult(reply="Unknown command. Try !help")
        return handler(args, ctx)

    def _handle_summon(self, args: str, ctx: CommandContext) -> CommandResult:
        if ctx.invoker_channel_id is None:
            return CommandResult(reply="Cannot determine your channel.")
        if not self.is_allowed_channel(ctx.invoker_channel_name):
            return CommandResult(
                reply=f"Cannot join channel '{ctx.invoker_channel_name}' — not in allowed channels list."
            )
        return CommandResult(
            reply=f"Summoned by {ctx.invoker_name} — joining channel!",
            move_to_channel_id=ctx.invoker_channel_id,
        )

    def _handle_leave(self, args: str, ctx: CommandContext) -> CommandResult:
        if ctx.home_channel_id is None:
            return CommandResult(reply="Home channel not configured.")
        if ctx.current_channel_id == ctx.home_channel_id:
            return CommandResult(reply="Already in home channel.")
        return CommandResult(
            reply="Leaving channel — returning to home.",
            move_to_home=True,
        )

    def _handle_voice(self, args: str, ctx: CommandContext) -> CommandResult:
        mode = args.strip().lower()
        if mode not in ("on", "off", "tts"):
            return CommandResult(
                reply=f"Unknown voice mode '{args.strip()}'. Use on, off, or tts.\n{VOICE_HELP}"
            )
        return CommandResult(
            reply=f"Voice mode set to '{mode}'.",
            set_voice_mode=mode,
        )

    def _handle_status(self, args: str, ctx: CommandContext) -> CommandResult:
        uptime_str = self._format_uptime(ctx.uptime_seconds)
        return CommandResult(
            reply=(
                f"Channel: {ctx.current_channel_name} (ID {ctx.current_channel_id})\n"
                f"Voice mode: {ctx.voice_mode}\n"
                f"Uptime: {uptime_str}"
            )
        )

    def _handle_help(self, args: str, ctx: CommandContext) -> CommandResult:
        return CommandResult(reply=COMMANDS_HELP)

    @staticmethod
    def _format_uptime(seconds: float) -> str:
        m, s = divmod(int(seconds), 60)
        h, m = divmod(m, 60)
        parts = []
        if h:
            parts.append(f"{h}h")
        if m or h:
            parts.append(f"{m}m")
        parts.append(f"{s}s")
        return " ".join(parts)
