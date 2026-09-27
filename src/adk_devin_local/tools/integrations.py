"""Optional Telegram, speech and structured-decision integrations."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

import httpx


class IntegrationTools:
    def __init__(self):
        self.token = os.environ.get("TG_BOT_TOKEN") or os.environ.get("TELEGRAM_BOT_TOKEN", "")
        self.chat = os.environ.get("TG_CHAT") or os.environ.get("TELEGRAM_CHAT_ID", "")
        self.allow_mutations = os.environ.get("ADK_DEVIN_ALLOW_MUTATIONS") == "1"

    def _write_gate(self) -> dict[str, str] | None:
        if not self.allow_mutations:
            return {"error":"Telegram writes are disabled; set ADK_DEVIN_ALLOW_MUTATIONS=1 in the trusted host environment."}
        return None

    async def _tg(self, method: str, payload: dict[str, Any], *, file_key: str = "", file_path: str = "") -> Any:
        if not self.token: return {"error": "TG_BOT_TOKEN is not configured."}
        url=f"https://api.telegram.org/bot{self.token}/{method}"
        async with httpx.AsyncClient(timeout=30) as client:
            if file_key and file_path:
                with open(file_path,"rb") as stream:
                    response=await client.post(url,data={k:str(v) for k,v in payload.items()},files={file_key:(Path(file_path).name,stream)})
            else:
                response=await client.post(url,json=payload)
        try: body=response.json()
        except ValueError: return {"error":f"Telegram HTTP {response.status_code}"}
        return body if body.get("ok") else {"error":body.get("description","Telegram API error")}

    async def tg_send(self, text: str, chat_id: str = "", reply_to: int = 0, thread_id: int = 0) -> Any:
        """Send a Telegram message using the configured bot identity."""
        denied=self._write_gate()
        if denied:return denied
        chat=chat_id or self.chat
        if not chat: return {"error":"Set TG_CHAT or pass chat_id."}
        payload={"chat_id":chat,"text":text[:4000]}
        if reply_to: payload["reply_to_message_id"]=reply_to
        topic=thread_id or int(os.environ.get("TG_THREAD","0") or 0)
        if topic: payload["message_thread_id"]=topic
        return await self._tg("sendMessage",payload)

    async def tg_react(self, message_id: int, emoji: str, chat_id: str = "") -> Any:
        """React to a Telegram message with one emoji."""
        denied=self._write_gate()
        if denied:return denied
        chat=chat_id or self.chat
        if not chat: return {"error":"Set TG_CHAT or pass chat_id."}
        return await self._tg("setMessageReaction",{"chat_id":chat,"message_id":message_id,"reaction":[{"type":"emoji","emoji":emoji}]})

    async def tg_pin(self, message_id: int, chat_id: str = "", disable_notification: bool = True) -> Any:
        """Pin a message in a Telegram chat."""
        denied=self._write_gate()
        if denied:return denied
        chat=chat_id or self.chat
        if not chat: return {"error":"Set TG_CHAT or pass chat_id."}
        return await self._tg("pinChatMessage",{"chat_id":chat,"message_id":message_id,"disable_notification":disable_notification})

    async def tg_edit(self, message_id: int, text: str, chat_id: str = "") -> Any:
        """Edit a message sent by this bot."""
        denied=self._write_gate()
        if denied:return denied
        chat=chat_id or self.chat
        if not chat: return {"error":"Set TG_CHAT or pass chat_id."}
        return await self._tg("editMessageText",{"chat_id":chat,"message_id":message_id,"text":text[:4000]})

    async def tg_delete(self, message_id: int, chat_id: str = "") -> Any:
        """Delete a Telegram message; bot permissions and age limits apply."""
        denied=self._write_gate()
        if denied:return denied
        chat=chat_id or self.chat
        if not chat: return {"error":"Set TG_CHAT or pass chat_id."}
        return await self._tg("deleteMessage",{"chat_id":chat,"message_id":message_id})

    async def tg_unpin(self, message_id: int = 0, chat_id: str = "") -> Any:
        """Unpin one message, or all pinned messages when message_id is zero."""
        denied=self._write_gate()
        if denied:return denied
        chat=chat_id or self.chat
        if not chat: return {"error":"Set TG_CHAT or pass chat_id."}
        payload={"chat_id":chat}
        if message_id: payload["message_id"]=message_id
        return await self._tg("unpinChatMessage",payload)

    async def tg_history(self, query: str, limit: int = 20) -> Any:
        """Search the host's Telegram journal through its PI_TEAM_DIR mailbox."""
        directory=os.environ.get("PI_TEAM_DIR")
        if not directory: return {"error":"PI_TEAM_DIR not configured; Telegram journal is host-owned."}
        import uuid
        reqdir=Path(directory)/"requests"; repdir=Path(directory)/"replies"
        reqdir.mkdir(parents=True,exist_ok=True); repdir.mkdir(parents=True,exist_ok=True)
        rid=uuid.uuid4().hex
        request={"id":rid,"from":os.environ.get("PI_TEAM_FROM","adk"),"to":"host","kind":"tg_history","text":json.dumps({"query":query,"limit":max(1,min(limit,100))}),"at":time.time()}
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

    async def tg_voice(self, text: str, chat_id: str = "", thread_id: int = 0) -> Any:
        """Speak text with edge-tts/espeak, then send it as a Telegram voice message."""
        denied=self._write_gate()
        if denied:return denied
        chat=chat_id or self.chat
        if not chat: return {"error":"Set TG_CHAT or pass chat_id."}
        if len(text)>4000: return {"error":"Text too long (maximum 4000 characters)."}
        with tempfile.TemporaryDirectory(prefix="adk-voice-") as directory:
            out=Path(directory)/"speech.mp3"
            if shutil.which("edge-tts"):
                proc=subprocess.run(["edge-tts","--text",text,"--write-media",str(out)],capture_output=True,text=True,timeout=90)
                if proc.returncode: return {"error":proc.stderr[-500:]}
            elif shutil.which("espeak"):
                out=Path(directory)/"speech.wav"
                proc=subprocess.run(["espeak","-w",str(out),text],capture_output=True,text=True,timeout=60)
                if proc.returncode:return {"error":proc.stderr[-500:]}
            else:return {"error":"Install edge-tts or espeak for speech synthesis."}
            payload={"chat_id":chat}
            topic=thread_id or int(os.environ.get("TG_THREAD","0") or 0)
            if topic:payload["message_thread_id"]=topic
            return await self._tg("sendVoice",payload,file_key="voice",file_path=str(out))

    async def tg_transcribe(self, file_id: str, language: str = "fa") -> Any:
        """Download Telegram audio and transcribe via Groq/OpenAI Whisper API."""
        if not self.token:return {"error":"TG_BOT_TOKEN is not configured."}
        api_key=os.environ.get("GROQ_API_KEY") or os.environ.get("OPENAI_API_KEY")
        if not api_key:return {"error":"Set GROQ_API_KEY or OPENAI_API_KEY for transcription."}
        base="https://api.groq.com/openai/v1" if os.environ.get("GROQ_API_KEY") else "https://api.openai.com/v1"
        model=os.environ.get("GROQ_STT_MODEL","whisper-large-v3-turbo") if "groq.com" in base else "whisper-1"
        async with httpx.AsyncClient(timeout=90) as client:
            meta=(await client.get(f"https://api.telegram.org/bot{self.token}/getFile",params={"file_id":file_id})).json()
            if not meta.get("ok"):return {"error":meta.get("description","Could not resolve Telegram file id")}
            remote=meta["result"]["file_path"]
            download=await client.get(f"https://api.telegram.org/file/bot{self.token}/{remote}")
            download.raise_for_status()
            response=await client.post(f"{base}/audio/transcriptions",headers={"Authorization":f"Bearer {api_key}"},
                data={"model":model,"language":language[:10]},files={"file":(Path(remote).name,download.content,"application/octet-stream")})
            response.raise_for_status()
            return {"text":response.json().get("text","")}

    async def _jev(self, instructions: str, candidates: dict[str,str], state: str) -> Any:
        key=os.environ.get("OPENROUTER_API_KEY")
        if not key:return {"error":"OPENROUTER_API_KEY not configured; decision service unavailable."}
        async with httpx.AsyncClient(timeout=20) as client:
            response=await client.post("https://openrouter.ai/api/alpha/decisions",
                headers={"Authorization":f"Bearer {key}","X-Title":"adk-devin-local","Content-Type":"application/json"},
                json={"model":os.environ.get("OPENROUTER_MODEL","typesafe/jev-1.13"),"state":{"message":state[:2000]},
                      "questions":{"pick":{"type":"choice","instructions":instructions[:1000],"criteria":candidates}}})
            response.raise_for_status(); body=response.json()
        answer=next(iter((body.get("answers") or {}).values()),{})
        return {"choice":answer.get("choice"),"confidence":answer.get("confidence",0)}

    async def jev_decide(self, question: str, options: list[str], context: str = "") -> Any:
        """Ask the structured Jev decision service to choose exactly one option."""
        if not options:return {"error":"At least one option is required."}
        return await self._jev(question,{option:option for option in options[:30]},context or question)

    async def jev_pick(self, goal: str, items: list[str], context: str = "") -> Any:
        """Pick the best candidate for a goal using the Jev decision service."""
        if not items:return {"error":"At least one candidate is required."}
        criteria={f"item_{i+1}":item[:300] for i,item in enumerate(items[:30])}
        result=await self._jev(f"Choose the candidate best serving: {goal}",criteria,context or "\n".join(items))
        try:
            index=int(str(result.get("choice","")).removeprefix("item_"))-1
            result["picked"]=items[index] if 0<=index<len(items) else None
        except (ValueError,AttributeError):result["picked"]=None
        return result
