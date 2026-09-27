"""Read model IDs and metadata from the installed Devin CLI."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any


def cli_path() -> str:
    configured = os.environ.get("DEVIN_CLI")
    candidates = [configured, str(Path.home() / ".local/bin/devin"), shutil.which("devin")]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate
    raise RuntimeError("Devin CLI not found; install it or set DEVIN_CLI")


def list_models() -> list[dict[str, Any]]:
    """Return the live Devin CLI catalog as family records."""
    result = subprocess.run([cli_path(), "models", "list", "--format", "json"],
        check=True, capture_output=True, text=True, timeout=30)
    data = json.loads(result.stdout)
    families = data.get("families", []) if isinstance(data, dict) else []
    return [family for family in families if isinstance(family, dict)]


def model_uids() -> list[str]:
    return [variant["model_uid"] for family in list_models()
            for variant in family.get("variants", [])
            if isinstance(variant, dict) and isinstance(variant.get("model_uid"), str)]
