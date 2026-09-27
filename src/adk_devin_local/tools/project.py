"""Pi-plugin-compatible ADK tool module."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from .stateful import StatefulTools

class ProjectTools(StatefulTools):
    def project_list(self) -> list[dict[str, Any]]:
        """List locally registered project roots."""
        return self._load("projects.json", [])

    def project_register(self, name: str, path: str, description: str = "") -> str:
        """Register an existing project directory for reference (does not change cwd)."""
        root = Path(path).expanduser().resolve(strict=True)
        if not root.is_dir(): return "Project path is not a directory."
        rows = self._load("projects.json", [])
        if any(item.get("name") == name for item in rows): return "Project name already registered."
        rows.append({"name": name[:100], "path": str(root), "description": description[:1000]})
        self._save("projects.json", rows)
        return f"Registered project '{name}'."

    def project_forget(self, name: str) -> str:
        """Remove a project from this local registry; does not delete files."""
        rows = self._load("projects.json", [])
        filtered = [item for item in rows if item.get("name") != name]
        if len(filtered) == len(rows): return "Project not found."
        self._save("projects.json", filtered)
        return f"Forgot project '{name}'."

    def project_use(self, name: str) -> dict[str, str]:
        """Resolve a registered project name to its local path."""
        for item in self._load("projects.json", []):
            if item.get("name")==name:return {"name":name,"path":item["path"]}
        return {"error":"Project not found."}

    async def project_current(self) -> str:
        """Resolve current project context through the host mailbox when available."""
        return await self._mailbox_request("project", "current|||", 20)
