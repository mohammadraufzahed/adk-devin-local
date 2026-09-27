"""Pi-plugin-compatible ADK tool module."""
from __future__ import annotations

import time, uuid
from typing import Any
from .stateful import StatefulTools


class MemoryTools(StatefulTools):
    """Soul journal memory — prefers the host's `memory` mailbox op (shared
    journal store), falls back to the package-local memory.json."""

    async def memory_store(self, note: str, key: str = "default") -> str:
        """Persist a fact to long-term memory."""
        if not note.strip(): return "Memory note must not be empty."
        if self._e("PI_TEAM_DIR"):
            return await self._mailbox_request("memory", f"store|||{note[:8000]}", 20)
        data = self._load("memory.json", [])
        row = {"id": uuid.uuid4().hex[:12], "key": key[:100], "note": note[:8000], "at": time.time()}
        data.append(row); self._save("memory.json", data)
        return f"Stored memory {row['id']}."

    async def memory_recall(self, query: str = "", limit: int = 10, key: str = "") -> Any:
        """Search long-term memories (empty query = recent)."""
        if self._e("PI_TEAM_DIR"):
            return await self._mailbox_request(
                "memory", f"recall|||{query or ''}|||{max(1, min(limit, 50))}", 20
            )
        rows = self._load("memory.json", [])
        terms = query.lower().split()
        scored = []
        for row in rows:
            if key and row.get("key") != key: continue
            text = (row.get("key", "") + " " + row.get("note", "")).lower()
            score = sum(text.count(term) for term in terms)
            if not terms or score: scored.append((score, row))
        scored.sort(key=lambda item: (-item[0], -item[1].get("at", 0)))
        return [row for _, row in scored[:max(1, min(limit, 50))]]

    async def memory_forget(self, match: str) -> str:
        """Delete memories containing a substring."""
        if self._e("PI_TEAM_DIR"):
            return await self._mailbox_request("memory", f"forget|||{match[:500]}", 20)
        rows = self._load("memory.json", [])
        needle=match.lower()
        filtered = [row for row in rows if needle not in (row.get("note", "")).lower()]
        removed=len(rows)-len(filtered)
        if not removed:return "No matching memories found."
        self._save("memory.json", filtered)
        return f"Forgot {removed} matching memory/memories."
