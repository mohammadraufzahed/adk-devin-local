"""Pi-plugin-compatible ADK tool module."""
from __future__ import annotations

import json, os, time
from pathlib import Path
from typing import Any
from .telegram_base import TelegramApi

class TelegramTools(TelegramApi):
    async def tg_send(self, text: str, chat_id: str = "", reply_to: int = 0, thread_id: int = 0) -> Any:
        """Send a Telegram message using the configured bot identity."""
        denied=self._write_gate()
        if denied:return denied
        chat=chat_id or self.chat
        if not chat: return {"error":"Set TG_CHAT or pass chat_id."}
        payload: dict[str, Any] = {"chat_id":chat,"text":text[:4000]}
        if reply_to: payload["reply_to_message_id"]=reply_to
        topic=thread_id or int(self._e("TG_THREAD","0") or 0)
        if topic: payload["message_thread_id"]=topic
        return await self._tg("sendMessage",payload)

    async def tg_react(self, message_id: int, emoji: str, chat_id: str = "") -> Any:
        """React to a Telegram message with one emoji."""
        denied=self._write_gate()
        if denied:return denied
        chat=chat_id or self.chat
        if not chat: return {"error":"Set TG_CHAT or pass chat_id."}
        return await self._tg("setMessageReaction",{"chat_id":chat,"message_id":str(message_id),"reaction":[{"type":"emoji","emoji":emoji}]})

    async def tg_pin(self, message_id: int, chat_id: str = "", disable_notification: bool = True) -> Any:
        """Pin a message in a Telegram chat."""
        denied=self._write_gate()
        if denied:return denied
        chat=chat_id or self.chat
        if not chat: return {"error":"Set TG_CHAT or pass chat_id."}
        return await self._tg("pinChatMessage",{"chat_id":chat,"message_id":str(message_id),"disable_notification":disable_notification})

    async def tg_edit(self, message_id: int, text: str, chat_id: str = "") -> Any:
        """Edit a message sent by this bot."""
        denied=self._write_gate()
        if denied:return denied
        chat=chat_id or self.chat
        if not chat: return {"error":"Set TG_CHAT or pass chat_id."}
        return await self._tg("editMessageText",{"chat_id":chat,"message_id":str(message_id),"text":text[:4000]})

    async def tg_delete(self, message_id: int, chat_id: str = "") -> Any:
        """Delete a Telegram message; bot permissions and age limits apply."""
        denied=self._write_gate()
        if denied:return denied
        chat=chat_id or self.chat
        if not chat: return {"error":"Set TG_CHAT or pass chat_id."}
        return await self._tg("deleteMessage",{"chat_id":chat,"message_id":str(message_id)})

    async def tg_unpin(self, message_id: int = 0, chat_id: str = "") -> Any:
        """Unpin one message, or all pinned messages when message_id is zero."""
        denied=self._write_gate()
        if denied:return denied
        chat=chat_id or self.chat
        if not chat: return {"error":"Set TG_CHAT or pass chat_id."}
        payload={"chat_id":chat}
        if message_id: payload["message_id"]=str(message_id)
        return await self._tg("unpinChatMessage",payload)

    async def tg_history(self, query: str, limit: int = 20) -> Any:
        """Search the host's Telegram journal through its PI_TEAM_DIR mailbox."""
        directory=self._e("PI_TEAM_DIR")
        if not directory: return {"error":"PI_TEAM_DIR not configured; Telegram journal is host-owned."}
        import uuid
        reqdir=Path(directory)/"requests"; repdir=Path(directory)/"replies"
        reqdir.mkdir(parents=True,exist_ok=True); repdir.mkdir(parents=True,exist_ok=True)
        rid=uuid.uuid4().hex
        request={"id":rid,"from":self._e("PI_TEAM_FROM","adk"),"to":"host","kind":"tg_history","text":json.dumps({"query":query,"limit":max(1,min(limit,100))}),"at":time.time()}
        (reqdir/f"{rid}.json").write_text(json.dumps(request))
        deadline=time.monotonic()+30
        while time.monotonic()<deadline:
            reply=repdir/f"{rid}.json"
            if reply.exists():
                try:return json.loads(reply.read_text()).get("text","")
                except (ValueError,OSError):pass
            import asyncio
            await asyncio.sleep(.5)
        return {"error":f"Timed out waiting for Telegram host journal ({rid})."}
