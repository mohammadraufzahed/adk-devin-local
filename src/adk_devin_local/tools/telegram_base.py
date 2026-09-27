"""Shared async Telegram Bot API client for Telegram and voice tools."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from telegram import Bot, ReactionTypeEmoji
from telegram.error import TelegramError
from telegram.request import HTTPXRequest

from .env import EnvOverlay


class TelegramApi(EnvOverlay):
    def __init__(self, env: dict[str, str] | None = None):
        self.env = dict(env or {})
        self.token = self._e("TG_BOT_TOKEN") or self._e("TELEGRAM_BOT_TOKEN", "")
        self.chat = self._e("TG_CHAT") or self._e("TELEGRAM_CHAT_ID", "")
        self.allow_mutations = os.environ.get("ADK_DEVIN_ALLOW_MUTATIONS") == "1"

    def _write_gate(self) -> dict[str, str] | None:
        if not self.allow_mutations:
            return {"error": "Telegram writes are disabled; set ADK_DEVIN_ALLOW_MUTATIONS=1 in the trusted host environment."}
        return None

    def _bot(self) -> Bot:
        request = HTTPXRequest(connect_timeout=10, read_timeout=30, write_timeout=30, pool_timeout=10)
        return Bot(token=self.token, request=request)

    async def _tg(self, method: str, payload: dict[str, Any], *, file_key: str = "", file_path: str = "") -> Any:
        """Invoke a Bot API method through python-telegram-bot's typed async client."""
        if not self.token:
            return {"error": "TG_BOT_TOKEN is not configured."}
        method_map = {
            "sendMessage": "send_message",
            "setMessageReaction": "set_message_reaction",
            "pinChatMessage": "pin_chat_message",
            "editMessageText": "edit_message_text",
            "deleteMessage": "delete_message",
            "unpinChatMessage": "unpin_chat_message",
            "sendVoice": "send_voice",
        }
        name = method_map.get(method)
        if not name:
            return {"error": f"Unsupported Telegram method: {method}"}
        kwargs = dict(payload)
        if method == "setMessageReaction":
            kwargs["reaction"] = [ReactionTypeEmoji(item["emoji"]) for item in kwargs.get("reaction", [])]
        if method == "sendVoice":
            if not file_path:
                return {"error": "A voice file is required."}
            kwargs["voice"] = Path(file_path)
        bot = self._bot()
        initialized = False
        try:
            await bot.initialize()
            initialized = True
            result = await getattr(bot, name)(**kwargs)
            return result.to_dict() if hasattr(result, "to_dict") else result
        except (TelegramError, OSError, ValueError) as exc:
            return {"error": str(exc)[:1000]}
        finally:
            if initialized:
                await bot.shutdown()

    async def _telegram_file(self, file_id: str) -> tuple[str, bytes] | dict[str, str]:
        if not self.token:
            return {"error": "TG_BOT_TOKEN is not configured."}
        bot = self._bot()
        initialized = False
        try:
            await bot.initialize()
            initialized = True
            remote = await bot.get_file(file_id)
            content = bytes(await remote.download_as_bytearray())
            return (Path(remote.file_path or "audio.bin").name, content)
        except (TelegramError, OSError, ValueError) as exc:
            return {"error": str(exc)[:1000]}
        finally:
            if initialized:
                await bot.shutdown()
