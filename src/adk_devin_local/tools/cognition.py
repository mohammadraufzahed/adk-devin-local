"""Cognition-layer tools — skill/recall/user-model ops over the host's
`cog` mailbox kind (same wire protocol as pi-cognition on the pi runtime).
"""
from __future__ import annotations

import json
from typing import Any

from .stateful import StatefulTools


class CognitionTools(StatefulTools):
    async def _cog(self, op: str, payload: dict[str, Any]) -> str:
        return await self._mailbox_request(
            "cog", f"{op}|||{json.dumps(payload, ensure_ascii=False)}", 30
        )

    async def skill_save(self, name: str, body: str, desc: str = "", scope: str = "soul", auto: bool = False) -> str:
        """Save a reusable skill/recipe to the team's skill store."""
        return await self._cog("skill_save", {
            "name": name[:120], "body": body[:20000], "desc": desc[:300],
            "scope": scope, "auto": bool(auto),
        })

    async def skill_list(self) -> str:
        """List learned skills available to this soul."""
        return await self._cog("skill_list", {})

    async def skill_read(self, name: str) -> str:
        """Fetch the full body of a saved skill by name."""
        return await self._cog("skill_read", {"name": name[:120]})

    async def skill_forget(self, name: str, scope: str = "soul") -> str:
        """Remove a saved skill."""
        return await self._cog("skill_forget", {"name": name[:120], "scope": scope})

    async def recall_search(self, q: str, limit: int = 5, days: int = 30, soul: str = "") -> str:
        """Full-text search across past run transcripts (cross-session recall)."""
        return await self._cog("recall", {
            "q": q[:500], "limit": max(1, min(int(limit or 5), 20)),
            "days": max(1, min(int(days or 30), 365)), "soul": soul[:80],
        })

    async def user_note(self, user: str, note: str) -> str:
        """Remember a durable fact about a user (preference, decision, context)."""
        return await self._cog("user_note", {"user": user[:120], "note": note[:2000]})

    async def user_recall(self, user: str = "") -> str:
        """Read user-model notes (optionally filtered to one user)."""
        return await self._cog("user_recall", {"user": user[:120]})

    async def user_forget(self, user: str, match: str = "") -> str:
        """Prune user-model notes containing a substring."""
        return await self._cog("user_forget", {"user": user[:120], "match": match[:300]})
