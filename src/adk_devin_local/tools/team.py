"""Pi-plugin-compatible ADK tool module."""
from __future__ import annotations

import asyncio, json, os, time, uuid
from pathlib import Path
from .stateful import StatefulTools

class TeamTools(StatefulTools):
    def team_roster(self) -> list[str]:
        """List available soul/agent identities from SOULS_DIR."""
        directory = self._e("SOULS_DIR")
        if not directory: return ["No SOULS_DIR configured."]
        return sorted(path.stem for path in Path(directory).glob("*.md"))

    def team_say(self, message: str, to: str = "all") -> str:
        """Send a non-blocking request to the configured Pi team mailbox."""
        directory = self._e("PI_TEAM_DIR")
        if not directory: return "PI_TEAM_DIR is not configured; no team mailbox is available."
        target = Path(directory) / "requests"; target.mkdir(parents=True, exist_ok=True)
        rid = uuid.uuid4().hex
        request = {"id": rid, "from": self._e("PI_TEAM_FROM", "adk"), "to": to,
                   "kind": "say", "text": message[:8000], "at": int(time.time() * 1000)}
        (target / f"{rid}.json").write_text(json.dumps(request), encoding="utf-8")
        return f"Team message queued ({rid})."

    async def team_ask(self, to: str, question: str, timeout_seconds: int = 120) -> str:
        """Ask a teammate via PI_TEAM_DIR mailbox and wait for its host watcher to reply."""
        directory = self._e("PI_TEAM_DIR")
        if not directory: return "PI_TEAM_DIR is not configured; no team mailbox is available."
        target = Path(directory); reqdir = target / "requests"; repdir = target / "replies"
        reqdir.mkdir(parents=True, exist_ok=True); repdir.mkdir(parents=True, exist_ok=True)
        rid = uuid.uuid4().hex
        req = {"id": rid, "from": self._e("PI_TEAM_FROM", "adk"), "to": to,
               "kind": "ask", "text": question[:8000], "at": int(time.time() * 1000)}
        (reqdir / f"{rid}.json").write_text(json.dumps(req), encoding="utf-8")
        deadline = time.monotonic() + max(1, min(timeout_seconds, 600))
        while time.monotonic() < deadline:
            reply = repdir / f"{rid}.json"
            if reply.exists():
                try: return json.loads(reply.read_text()).get("text", "(empty reply)")
                except (ValueError, OSError): return "Received an unreadable team reply."
            import asyncio
            await asyncio.sleep(1)
        return f"Timed out waiting for teammate; request {rid} remains queued."

    def team_task(self, to: str, task: str, budget_min: int = 10) -> str:
        """Delegate work asynchronously through the Pi team host mailbox."""
        directory=self._e("PI_TEAM_DIR")
        if not directory:return "PI_TEAM_DIR is not configured; no team mailbox is available."
        reqdir=Path(directory)/"requests"; reqdir.mkdir(parents=True,exist_ok=True)
        rid=uuid.uuid4().hex
        request={"id":rid,"from":self._e("PI_TEAM_FROM","adk"),"to":to,"kind":"task","text":task[:8000],"budget_s":max(60,min(budget_min,120))*60,"at":int(time.time() * 1000)}
        (reqdir/f"{rid}.json").write_text(json.dumps(request),encoding="utf-8")
        return f"Task delegated to {to} ({rid}); host watcher must be running."

    def team_emit(self, event: str, payload: str = "", to: str = "auto") -> str:
        """Emit a typed event to subscribed agents through the team mailbox."""
        directory=self._e("PI_TEAM_DIR")
        if not directory:return "PI_TEAM_DIR is not configured; no team mailbox is available."
        reqdir=Path(directory)/"requests"; reqdir.mkdir(parents=True,exist_ok=True)
        rid=uuid.uuid4().hex
        request={"id":rid,"from":self._e("PI_TEAM_FROM","adk"),"to":to,"kind":"event","text":event[:120]+(" "+payload[:7000] if payload else ""),"at":int(time.time() * 1000)}
        (reqdir/f"{rid}.json").write_text(json.dumps(request),encoding="utf-8")
        return f"Event {event} emitted ({rid})."

    async def team_status(self) -> str:
        """Ask the host watcher for team queue and activity status."""
        return await self._mailbox_request("status", "", 15)

    def team_handoff(self, to: str, task: str) -> str:
        """Hand a request to a team member; host mailbox watcher must be running."""
        directory = self._e("PI_TEAM_DIR")
        if not directory: return "PI_TEAM_DIR is not configured; no team mailbox is available."
        reqdir = Path(directory) / "requests"; reqdir.mkdir(parents=True, exist_ok=True)
        rid = uuid.uuid4().hex
        request = {"id": rid, "from": self._e("PI_TEAM_FROM", "adk"), "to": to,
                   "kind": "handoff", "text": task[:8000], "at": int(time.time() * 1000)}
        (reqdir / f"{rid}.json").write_text(json.dumps(request), encoding="utf-8")
        return f"Request handed to {to} ({rid}); the host mailbox watcher must be running."
