"""Pi-plugin-compatible ADK tool module."""
from __future__ import annotations

import time, uuid
from typing import Any
from .stateful import StatefulTools

class MemoryTools(StatefulTools):
    def memory_store(self, note: str, key: str = "default") -> str:
        """Persist a note in this workspace's local agent memory."""
        if not note.strip(): return "Memory note must not be empty."
        data = self._load("memory.json", [])
        row = {"id": uuid.uuid4().hex[:12], "key": key[:100], "note": note[:8000], "at": time.time()}
        data.append(row); self._save("memory.json", data)
        return f"Stored memory {row['id']}."

    def memory_recall(self, query: str = "", limit: int = 10, key: str = "") -> list[dict[str, Any]]:
        """Search notes persisted by memory_store."""
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

    def memory_forget(self, match: str) -> str:
        """Delete memories containing the supplied substring."""
        rows = self._load("memory.json", [])
        needle=match.lower()
        filtered = [row for row in rows if needle not in (row.get("note", "")).lower()]
        removed=len(rows)-len(filtered)
        if not removed:return "No matching memories found."
        self._save("memory.json", filtered)
        return f"Forgot {removed} matching memory/memories."
