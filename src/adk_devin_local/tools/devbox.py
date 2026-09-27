"""Pi-plugin-compatible ADK tool module."""
from __future__ import annotations

import json, re
from pathlib import Path
from .cli import CliTools

class DevboxTools(CliTools):
    def devbox_info(self) -> str:
        """Show devbox project information and declared packages."""
        if not (self.root / "devbox.json").exists(): return "No devbox.json in workspace."
        return self._run(["devbox", "info"])

    def devbox_config(self) -> str:
        """Read devbox.json configuration."""
        path = self.root / "devbox.json"
        if not path.is_file(): return "No devbox.json in workspace."
        try: return json.dumps(json.loads(path.read_text()), indent=2)
        except (OSError, ValueError) as exc: return f"Could not parse devbox.json: {exc}"

    def devbox_run(self, command: str, timeout: int = 120) -> str:
        """Run a command in the project's pinned devbox environment."""
        if not (self.root / "devbox.json").exists(): return "No devbox.json in workspace."
        # Explicit opt-in is required because this accepts a shell command.
        denied = self._mutate("devbox run (arbitrary command)")
        if denied: return denied
        return self._run(["devbox", "run", "--", "sh", "-lc", command], timeout=timeout)

    def devbox_services(self, action: str = "ls", name: str = "") -> str:
        """List or manage declared Devbox services (start/stop/restart/ls)."""
        if action not in {"ls", "start", "stop", "restart"}: return "Invalid service action."
        if action != "ls":
            denied = self._mutate(f"devbox services {action}")
            if denied: return denied
        args = ["devbox", "services", action]
        if name: args.append(name)
        return self._run(args, timeout=90)

    def devbox_search(self, package: str) -> str:
        """Search Nix packages before adding a dependency to a Devbox project."""
        return self._run(["devbox","search",package[:150]],timeout=45)

    def devbox_script(self, name: str, timeout: int = 120) -> str:
        """Run a named shell script from devbox.json."""
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}",name):return "Invalid script name."
        if not (self.root/"devbox.json").exists():return "No devbox.json in workspace."
        return self._run(["devbox","run",name],timeout=timeout)

    def devbox_env(self, filter: str = "") -> str:
        """Show devbox environment variables, optionally filtered by name."""
        if not (self.root/"devbox.json").exists():return "No devbox.json in workspace."
        result=self._run(["devbox","run","--","env"],timeout=45)
        if not filter:return result
        try:
            parsed=json.loads(result); output=parsed.get("output","")
            parsed["output"]="\\n".join(line for line in output.splitlines() if filter.lower() in line.lower())
            return json.dumps(parsed)
        except (ValueError,AttributeError):return result

    def devbox_generate(self, target: str = "dockerfile") -> str:
        """Generate a Devbox environment file (dockerfile, devcontainer, direnv)."""
        if target not in {"dockerfile","devcontainer","direnv"}:return "Invalid generation target."
        denied=self._mutate("devbox generate")
        if denied:return denied
        return self._run(["devbox","generate",target],timeout=90)

    def devbox_update(self) -> str:
        """Update pinned package versions in devbox.lock; requires host mutation opt-in."""
        denied=self._mutate("devbox update")
        if denied:return denied
        return self._run(["devbox","update"],timeout=180)

    def devbox_package(self, action: str, package: str) -> str:
        """Add or remove one Devbox package; requires host mutation opt-in."""
        if action not in {"add","remove"} or not re.fullmatch(r"[A-Za-z0-9_.+-]{1,120}",package):return "Invalid package/action."
        denied=self._mutate(f"devbox {action}")
        if denied:return denied
        return self._run(["devbox",action,package],timeout=180)

    def devbox_init(self, packages: list[str] | None = None) -> str:
        """Initialize devbox.json with optional packages; requires host mutation opt-in."""
        denied=self._mutate("devbox init")
        if denied:return denied
        if (self.root/"devbox.json").exists():return "devbox.json already exists."
        args=["devbox","init"]
        for package in (packages or [])[:20]:
            if not re.fullmatch(r"[A-Za-z0-9_.+-]{1,120}",package):return "Invalid package name."
            args.extend(["--package",package])
        return self._run(args,timeout=120)
