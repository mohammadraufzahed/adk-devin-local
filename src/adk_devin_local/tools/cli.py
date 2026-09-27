"""Shared command runner for the individual Pi plugin adapters."""
from __future__ import annotations
import json, os, shutil, subprocess
from pathlib import Path
from typing import Any

from .env import EnvOverlay

class CliTools(EnvOverlay):
    def __init__(self, root: str | Path, env: dict[str, str] | None = None):
        self.root = Path(root).expanduser().resolve(strict=True)
        # Per-run env overlay (e.g. soul identity: GH_TOKEN, PI_TEAM_*,
        # gh-shim PATH). Merged over the ambient process env per call.
        self.env = dict(env or {})
        self.allow_mutations = os.environ.get("ADK_DEVIN_ALLOW_MUTATIONS") == "1"

    def _run(self, argv: list[str], timeout: int = 45) -> str:
        if not shutil.which(argv[0]):
            return f"Tool unavailable: {argv[0]} is not installed."
        env = os.environ | self.env if self.env else None
        try:
            proc = subprocess.run(argv, cwd=self.root, env=env, capture_output=True, text=True,
                timeout=max(1, min(timeout, 300)), check=False)
        except subprocess.TimeoutExpired:
            return f"Command timed out after {timeout}s."
        output = (proc.stdout + ("\n" + proc.stderr if proc.stderr else "")).strip()
        if len(output) > 20_000:
            output = output[:20_000] + "\n[truncated]"
        return json.dumps({"exit_code": proc.returncode, "output": output}, ensure_ascii=False)

    def _mutate(self, command: str) -> str | None:
        if not self.allow_mutations:
            return f"{command} is disabled. Set ADK_DEVIN_ALLOW_MUTATIONS=1 in the host environment to enable write operations."
        return None
