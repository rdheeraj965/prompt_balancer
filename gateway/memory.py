import json
from typing import List, Dict
from django.core.cache import cache

class ConversationMemory:
    PREFIX = "prompt_balancer:chat:"
    MAX_MESSAGES = 12  # Last 6 user-assistant turns
    TTL_SECONDS = 86400  # 24 hours

    @classmethod
    def get_history(cls, session_id: str) -> List[Dict[str, str]]:
        if not session_id:
            return []
        raw = cache.get(f"{cls.PREFIX}{session_id}")
        return json.loads(raw) if raw else []

    @classmethod
    def append_turn(cls, session_id: str, user_prompt: str, assistant_reply: str) -> None:
        if not session_id or not assistant_reply.strip():
            return
        history = cls.get_history(session_id)
        history.append({"role": "user", "content": user_prompt})
        history.append({"role": "assistant", "content": assistant_reply})
        history = history[-cls.MAX_MESSAGES :]
        cache.set(f"{cls.PREFIX}{session_id}", json.dumps(history), timeout=cls.TTL_SECONDS)

    @classmethod
    def clear(cls, session_id: str) -> None:
        if session_id:
            cache.delete(f"{cls.PREFIX}{session_id}")

    @classmethod
    def estimate_history_tokens(cls, history: List[Dict[str, str]]) -> int:
        total_words = sum(len(msg["content"].split()) for msg in history)
        return int(total_words * 1.3)

    @classmethod
    def sync_history(cls, session_id: str, messages: List[Dict[str, str]]) -> None:
        if not session_id:
            return
        cleaned = [
            {"role": m["role"], "content": m["content"]}
            for m in messages
            if m.get("role") in ("user", "assistant") and m.get("content")
        ]
        cache.set(
            f"{cls.PREFIX}{session_id}",
            json.dumps(cleaned[-cls.MAX_MESSAGES :]),
            timeout=cls.TTL_SECONDS,
        )