"""ADK wrappers for the CodeGraph CLI."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


class CodeGraphTools:
    def __init__(self, root: str | Path): self.root = Path(root).expanduser().resolve(strict=True)
    def _run(self, *args: str, timeout: int = 120) -> str:
        if not shutil.which("codegraph"): return "codegraph CLI not installed (npm i -g @colbymchenry/codegraph)."
        try:
            proc=subprocess.run(["codegraph", *args], cwd=self.root, capture_output=True, text=True, timeout=timeout)
            out=(proc.stdout + ("\n"+proc.stderr if proc.stderr else "")).strip()
            return f"exit {proc.returncode}\n{out[:16000]}"
        except subprocess.TimeoutExpired: return f"codegraph {args[0]} timed out."
    def codegraph_status(self) -> str:
        """Show CodeGraph index status for this project."""
        return self._run("status", timeout=30)
    def codegraph_init(self) -> str:
        """Build a CodeGraph index for this project (may take several minutes)."""
        if os.environ.get("ADK_DEVIN_ALLOW_MUTATIONS") != "1": return "Index creation disabled; set ADK_DEVIN_ALLOW_MUTATIONS=1 on the host."
        return self._run("init", timeout=600)
    def codegraph_sync(self) -> str:
        """Incrementally update this project's CodeGraph index."""
        if os.environ.get("ADK_DEVIN_ALLOW_MUTATIONS") != "1": return "Index sync disabled; set ADK_DEVIN_ALLOW_MUTATIONS=1 on the host."
        return self._run("sync", timeout=300)
    def codegraph_query(self, search: str) -> str:
        """Find symbols by name using CodeGraph."""
        return self._run("query", search[:500])
    def codegraph_context(self, task: str, max_nodes: int = 12) -> str:
        """Build code context for a task from the indexed graph."""
        return self._run("context", task[:1000], "--max-nodes", str(max(1,min(max_nodes,30))))
    def codegraph_explore(self, query: str) -> str:
        """Explore a code area with source and call paths."""
        return self._run("explore", query[:500])
    def codegraph_node(self, name: str) -> str:
        """Show one symbol's source and callers/callees."""
        return self._run("node", name[:300])
    def codegraph_files(self) -> str:
        """Show project file structure from CodeGraph."""
        return self._run("files")
