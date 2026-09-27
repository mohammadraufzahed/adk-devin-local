"""Pi-plugin-compatible ADK tool module."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from .stateful import StatefulTools

class ProjectTools(StatefulTools):
    """Project registry — routes to the host `project` mailbox op when
    PI_TEAM_DIR is set (shared projects table), else a local registry."""

    async def project_list(self) -> Any:
        """List registered projects (name, dir, repo, mode, topic)."""
        if self._e("PI_TEAM_DIR"):
            return await self._mailbox_request("project", "list|||", 20)
        return self._load("projects.json", [])

    async def project_register(self, name: str, path: str = "", description: str = "",
                               dir: str = "", repo: str = "", topic_id: int = 0) -> Any:
        """Register a project (name, dir, optional repo/topic)."""
        if self._e("PI_TEAM_DIR"):
            d = dir or path
            payload = f"{name}|{d}|{repo}|{topic_id or ''}"
            return await self._mailbox_request("project", f"register|||{payload}", 20)
        root = Path(dir or path).expanduser().resolve(strict=True)
        if not root.is_dir(): return "Project path is not a directory."
        rows = self._load("projects.json", [])
        if any(item.get("name") == name for item in rows): return "Project name already registered."
        rows.append({"name": name[:100], "path": str(root), "description": description[:1000]})
        self._save("projects.json", rows)
        return f"Registered project '{name}'."

    async def project_forget(self, name: str) -> Any:
        """Deregister a project by name."""
        if self._e("PI_TEAM_DIR"):
            return await self._mailbox_request("project", f"forget|||{name}", 20)
        rows = self._load("projects.json", [])
        filtered = [item for item in rows if item.get("name") != name]
        if len(filtered) == len(rows): return "Project not found."
        self._save("projects.json", filtered)
        return f"Forgot project '{name}'."

    async def project_use(self, name: str) -> Any:
        """Resolve a project name to its dir/repo (binds context on the host)."""
        if self._e("PI_TEAM_DIR"):
            return await self._mailbox_request("project", f"use|||{name}", 20)
        for item in self._load("projects.json", []):
            if item.get("name")==name:return {"name":name,"path":item["path"]}
        return {"error":"Project not found."}

    async def project_mode(self, name: str, mode: str) -> Any:
        """Set a project's lifecycle mode (develop|readonly|monitor|paused) — owner-gated on the host."""
        if self._e("PI_TEAM_DIR"):
            return await self._mailbox_request("project", f"mode|||{name}|{mode}", 20)
        return "project_mode requires the host mailbox (PI_TEAM_DIR); lifecycle state is host-owned."

    async def project_current(self) -> str:
        """Resolve current project context through the host mailbox when available."""
        return await self._mailbox_request("project", "current|||", 20)
