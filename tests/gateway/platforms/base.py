from abc import ABC, abstractmethod


class MessageType:
    TEXT = "text"
    VOICE = "voice"


class SessionSource:
    def __init__(self, platform: str = "", chat_id: str = "", user_id: str = "",
                 user_name: str = ""):
        self.platform = platform
        self.chat_id = chat_id
        self.user_id = user_id
        self.user_name = user_name


class MessageEvent:
    def __init__(self, source: "SessionSource | None" = None, chat_id: str = "",
                 content: str = "", type: str = "", metadata: dict | None = None):
        self.source = source
        self.chat_id = chat_id
        self.content = content
        self.type = type
        self.metadata = metadata or {}


class SendResult:
    def __init__(self, success: bool = False, message_id: str = ""):
        self.success = success
        self.message_id = message_id


class BasePlatformAdapter(ABC):
    def __init__(self, config: PlatformConfig, platform: object):
        self.config = config
        self.platform = platform

    @abstractmethod
    async def connect(self) -> bool:
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        ...

    @abstractmethod
    async def send(self, chat_id: str, content: str, reply_to: str | None = None,
                   metadata: dict | None = None) -> SendResult:
        ...

    @abstractmethod
    async def get_chat_info(self, chat_id: str) -> dict:
        ...

    async def handle_message(self, event: MessageEvent) -> None:
        pass

    async def send_voice(self, chat_id: str, audio_path: str, caption: str = "",
                         reply_to: str | None = None, metadata: dict | None = None,
                         **kwargs) -> SendResult:
        return SendResult(success=True, message_id="")

    async def play_tts(self, chat_id: str, audio_path: str, **kwargs) -> SendResult:
        return SendResult(success=True, message_id="")

    def build_source(self, chat_id: str, chat_name: str = "", chat_type: str = "",
                     user_id: str = "", user_name: str = "") -> SessionSource:
        return SessionSource(
            platform=str(self.platform), chat_id=chat_id,
            user_id=user_id, user_name=user_name,
        )
