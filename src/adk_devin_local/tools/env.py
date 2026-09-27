"""Per-run environment overlay shared by all tool classes.

Every tool instance may carry an ``env`` dict injected by the host
(e.g. a soul's identity: GH_TOKEN, TG_BOT_TOKEN, PI_TEAM_*). Lookups
go through :meth:`_e` — the overlay wins over the ambient process
environment, so a soul always acts under its own identity.
"""
from __future__ import annotations

import os
from typing import Any


class EnvOverlay:
    """Mixin: ``self.env`` overlay + ``self._e(key, default)`` lookup."""

    env: dict[str, str] = {}

    def _e(self, key: str, default: Any = None) -> Any:
        if key in self.env:
            return self.env[key]
        return os.environ.get(key, default)

    def _merged_env(self) -> dict[str, str]:
        return {**os.environ, **self.env}
