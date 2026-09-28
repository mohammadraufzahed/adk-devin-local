"""Shared JSON state and mailbox utilities for individual Pi plugin adapters."""
from __future__ import annotations
import json, os, time, uuid
from pathlib import Path
from typing import Any

from .env import EnvOverlay

class StatefulTools(EnvOverlay):
    def __init__(self, root: str | Path, state_dir: str | Path | None = None, env: dict[str, str] | None = None):
        self.env = dict(env or {})
        self.root = Path(root).expanduser().resolve(strict=True)
        self.state = Path(state_dir or self._e("ADK_DEVIN_STATE_DIR", self.root / ".adk-devin")).expanduser().resolve()
        self.state.mkdir(parents=True, exist_ok=True)

    def _load(self, name: str, default: Any) -> Any:
        path = self.state / name
        try: return json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError: return default
        except (OSError, ValueError): return default

    def _save(self, name: str, value: Any) -> None:
        path = self.state / name
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temp, path)

    async def _mailbox_request(self, kind: str, text: str, timeout: int) -> str:
        directory=self._e("PI_TEAM_DIR")
        if not directory:return f"PI_TEAM_DIR is not configured; cannot query host {kind}."
        target=Path(directory); reqdir=target/"requests"; repdir=target/"replies"
        reqdir.mkdir(parents=True,exist_ok=True); repdir.mkdir(parents=True,exist_ok=True)
        rid=uuid.uuid4().hex
        request={"id":rid,"from":self._e("PI_TEAM_FROM","adk"),"to":"host","kind":kind,"text":text,"at":int(time.time() * 1000)}
        (reqdir/f"{rid}.json").write_text(json.dumps(request),encoding="utf-8")
        import asyncio
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            reply=repdir/f"{rid}.json"
            if reply.exists():
                try:return str(json.loads(reply.read_text()).get("text",""))
                except (ValueError,OSError):pass
            await asyncio.sleep(.5)
        return f"Host {kind} request timed out ({rid})."
