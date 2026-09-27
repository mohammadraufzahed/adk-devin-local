"""Pi-plugin-compatible ADK tool module."""
from __future__ import annotations

import json, shutil
from .cli import CliTools

class DependencyTools(CliTools):
    def deps_audit(self) -> str:
        """Run available package-manager security audit commands for this project."""
        found = []
        for name, args in (("npm", ["audit", "--omit=dev", "--json"]),
                           ("pip-audit", ["-r", "requirements.txt", "-f", "json"]),
                           ("cargo", ["audit", "--json"]), ("govulncheck", ["./..."])):
            if shutil.which(name) and ((self.root / "package-lock.json").exists() if name == "npm" else
                (self.root / "requirements.txt").exists() if name == "pip-audit" else
                (self.root / "Cargo.lock").exists() if name == "cargo" else (self.root / "go.mod").exists()):
                found.append(f"[{name}] {self._run([name, *args], timeout=180)}")
        return "\n".join(found) if found else "No supported dependency lockfiles/tools found."

    def deps_outdated(self) -> str:
        """List outdated npm dependencies when a package.json is present."""
        if not (self.root / "package.json").exists(): return "No package.json found."
        return self._run(["npm", "outdated", "--json"], timeout=90)

    def deps_licenses(self) -> str:
        """Summarize production dependency licenses from package-lock.json when available."""
        lock=self.root/"package-lock.json"
        if not lock.is_file():return "No package-lock.json found; license audit for this ecosystem is unavailable."
        try:data=json.loads(lock.read_text(encoding="utf-8"))
        except (OSError,ValueError) as exc:return f"Could not read package-lock.json: {exc}"
        packages=data.get("packages",{})
        rows=[]
        for path,package in packages.items():
            if not path or path.count("node_modules/")>1 or package.get("dev"):continue
            rows.append({"name":path.rsplit("node_modules/",1)[-1],"version":package.get("version"),"license":package.get("license","unknown")})
        return json.dumps(rows[:1000],ensure_ascii=False)

    def deps_update(self, scope: str = "patch", ecosystem: str = "npm") -> str:
        """Safely update production dependencies; requires host mutation opt-in."""
        denied = self._mutate("dependency update")
        if denied: return denied
        if scope not in {"patch", "minor"}: return "Only patch or minor updates are supported."
        if ecosystem=="npm" and (self.root/"package-lock.json").exists():
            return self._run(["npm","update","--save"],timeout=240)
        if ecosystem=="cargo" and (self.root/"Cargo.lock").exists():
            return self._run(["cargo","update"],timeout=300)
        if ecosystem=="go" and (self.root/"go.mod").exists():
            flag="-u=patch" if scope=="patch" else "-u"
            return self._run(["go","get",flag,"./..."],timeout=300)
        if ecosystem=="python" and (self.root/"uv.lock").exists():
            return self._run(["uv","lock","--upgrade"],timeout=300)
        return f"No supported {ecosystem} lockfile found (supported: npm, cargo, go, python)."
