def build_session_key(platform: str, chat_id: str, user_id: str) -> str:
    return f"{platform}:{chat_id}:{user_id}"
