"""Voice synthesis and transcription tools using Edge TTS and OpenAI-compatible APIs."""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import edge_tts
from openai import AsyncOpenAI
from .telegram_base import TelegramApi


class VoiceTools(TelegramApi):
    async def tg_voice(self, text: str, chat_id: str = "", thread_id: int = 0) -> Any:
        """Synthesize speech with edge-tts and send it as a Telegram voice message."""
        denied = self._write_gate()
        if denied:
            return denied
        chat = chat_id or self.chat
        if not chat:
            return {"error": "Set TG_CHAT or pass chat_id."}
        if len(text) > 4000:
            return {"error": "Text too long (maximum 4000 characters)."}
        with tempfile.TemporaryDirectory(prefix="adk-voice-") as directory:
            output = Path(directory) / "speech.mp3"
            try:
                voice = self._e("EDGE_TTS_VOICE", "fa-IR-DilaraNeural")
                await edge_tts.Communicate(text, voice=voice).save(str(output))
            except Exception as exc:
                # Keep the local speech engine as an offline fallback.
                if not shutil.which("espeak"):
                    return {"error": f"Edge TTS failed: {exc}"}
                output = Path(directory) / "speech.wav"
                try:
                    proc = subprocess.run(["espeak", "-w", str(output), text], capture_output=True, text=True, timeout=60)
                except (OSError, subprocess.TimeoutExpired) as fallback_exc:
                    return {"error": f"Speech synthesis failed: {fallback_exc}"}
                if proc.returncode:
                    return {"error": proc.stderr[-500:]}
            payload: dict[str, Any] = {"chat_id": chat}
            topic = thread_id or int(self._e("TG_THREAD", "0") or 0)
            if topic:
                payload["message_thread_id"] = topic
            return await self._tg("sendVoice", payload, file_key="voice", file_path=str(output))

    async def tg_transcribe(self, file_id: str, language: str = "fa") -> Any:
        """Download Telegram audio and transcribe it with the OpenAI async SDK."""
        api_key = self._e("GROQ_API_KEY") or self._e("OPENAI_API_KEY")
        if not api_key:
            return {"error": "Set GROQ_API_KEY or OPENAI_API_KEY for transcription."}
        audio = await self._telegram_file(file_id)
        if isinstance(audio, dict):
            return audio
        filename, content = audio
        groq = bool(self._e("GROQ_API_KEY"))
        model = self._e("GROQ_STT_MODEL", "whisper-large-v3-turbo") if groq else "whisper-1"
        base_url = "https://api.groq.com/openai/v1" if groq else None
        try:
            async with AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=90) as client:
                result = await client.audio.transcriptions.create(
                    model=model,
                    file=(filename, content, "application/octet-stream"),
                    language=language[:10],
                )
            return {"text": result.text}
        except Exception as exc:
            return {"error": f"Transcription failed: {exc}"}
