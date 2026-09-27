"""Shared command runner for the individual Pi plugin adapters."""
from __future__ import annotations
import json, os, shutil, subprocess
from pathlib import Path
from typing import Any

class CliTools:
    def __init__(self, root: str | Path):
        self.root = Path(root).expanduser().resolve(strict=True)
        self.allow_mutations = os.environ.get("ADK_DEVIN_ALLOW_MUTATIONS") == "1"

    def _run(self, argv: list[str], timeout: int = 45) -> str:
        if not shutil.which(argv[0]):
            return f"Tool unavailable: {argv[0]} is not installed."
        try:
            proc = subprocess.run(argv, cwd=self.root, capture_output=True, text=True,
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
