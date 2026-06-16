"""TeamSpeak 3 platform adapter for Hermes Agent."""

from gateway.config import Platform

from .adapter import TeamSpeakAdapter

__version__ = "0.1.0"


def register(ctx) -> None:
    """Hermes plugin entry point — called by the plugin system at gateway startup."""
    ctx.register_platform(
        name="teamspeak3",
        label="TeamSpeak 3",
        adapter_factory=lambda cfg: TeamSpeakAdapter(cfg, Platform("teamspeak3")),
        check_fn=_check_requirements,
        required_env=[
            "TS3_SERVER_HOST",
            "TS3_SERVERQUERY_USER",
            "TS3_SERVERQUERY_PASS",
        ],
        install_hint="pip install hermes-agent-ts3",
        cron_deliver_env_var="TS3_HOME_CHANNEL",
        allowed_users_env="TS3_ALLOWED_USERS",
        allow_all_env="TS3_ALLOW_ALL_USERS",
        max_message_length=1024,
        emoji="🎙️",
        allow_update_command=True,
        platform_hint=(
            "You are communicating on TeamSpeak 3. "
            "Keep responses concise. Voice responses will be spoken aloud."
        ),
    )


def _check_requirements() -> bool:
    try:
        import sounddevice  # noqa: F401

        return True
    except ImportError:
        return False
