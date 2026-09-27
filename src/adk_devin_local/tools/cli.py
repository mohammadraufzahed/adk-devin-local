"""Workspace-scoped adapters for common local developer CLIs."""
from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
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

    # Git — each tool is intentionally narrow; no arbitrary git subcommands.
    def git_status(self) -> str:
        """Show branch and working-tree status for the configured repository."""
        return self._run(["git", "status", "--short", "--branch"])

    def git_diff(self, target: str = "", stat: bool = False) -> str:
        """Show staged/unstaged or between-ref diffs; target may be --staged, HEAD~3 or a branch."""
        args=["git","diff"]
        if stat:args.append("--stat")
        if target=="--staged":args.append("--staged")
        elif target:
            if target.startswith("-") or ".." in target:return "Invalid diff target."
            args.append(target)
        return self._run(args)

    def git_log(self, limit: int = 10) -> str:
        """Show recent commits (limit is capped at 50)."""
        return self._run(["git", "log", f"-{max(1, min(limit, 50))}", "--oneline", "--decorate"])

    def git_branch(self) -> str:
        """List local and remote branches."""
        return self._run(["git", "branch", "--all", "--verbose"])

    def git_branches(self) -> str:
        """Pi-compatible branch listing with upstream tracking information."""
        return self._run(["git","branch","-vv","--sort=-committerdate"])

    def git_show(self, ref: str = "HEAD", path: str = "") -> str:
        """Show a commit or a file at a commit."""
        if ref.startswith("-") or ".." in ref: return "Invalid git ref."
        args=["git","show",ref]
        if path:
            if Path(path).is_absolute() or ".." in Path(path).parts:return "Rejected path outside workspace."
            args.append("--"+path)
        return self._run(args)

    def git_blame(self, path: str, start: int = 0, end: int = 0) -> str:
        """Show line authorship for a repository file."""
        if Path(path).is_absolute() or ".." in Path(path).parts:return "Rejected path outside workspace."
        args=["git","blame"]
        if start>0 and end>=start:args.extend(["-L",f"{start},{min(end,start+500)}"])
        return self._run([*args,"--",path])

    def git_file_history(self, path: str, limit: int = 10) -> str:
        """Show commit history for a repository file."""
        if Path(path).is_absolute() or ".." in Path(path).parts:return "Rejected path outside workspace."
        return self._run(["git","log",f"-{max(1,min(limit,50))}","--oneline","--",path])

    def git_commit(self, message: str, paths: list[str] | None = None) -> str:
        """Commit staged changes or selected paths; requires host mutation opt-in."""
        denied = self._mutate("git commit")
        if denied: return denied
        if paths:
            for path in paths:
                if Path(path).is_absolute() or ".." in Path(path).parts:
                    return "Rejected path outside workspace."
            added = self._run(["git", "add", "--", *paths])
            try:
                if json.loads(added).get("exit_code") != 0: return added
            except (ValueError, AttributeError): return added
        return self._run(["git", "commit", "-m", message[:500]], timeout=90)

    def git_push(self, remote: str = "origin", branch: str = "") -> str:
        """Push a branch; requires ADK_DEVIN_ALLOW_MUTATIONS=1."""
        denied = self._mutate("git push")
        if denied: return denied
        if not remote.replace("-", "").replace("_", "").isalnum(): return "Invalid remote name."
        if branch and (branch.startswith("-") or ".." in branch or " " in branch): return "Invalid branch name."
        argv = ["git", "push", remote]
        if branch: argv.append(branch)
        return self._run(argv, timeout=120)

    # Docker — docker exec runs only observation commands unless mutations are enabled.
    def docker_list(self, all: bool = False) -> str:
        """List running containers; all=true includes stopped containers."""
        return self._run(["docker", "ps", "--format", "{{json .}}", *( ["--all"] if all else [])])

    def docker_ps(self, all: bool = False) -> str:
        """Pi-compatible alias: list container name, image, state and uptime."""
        return self.docker_list(all)

    def docker_logs(self, container: str, lines: int = 80, since: str = "") -> str:
        """Tail container logs (max 1000 lines)."""
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}",container):return "Invalid container name."
        if since and not re.fullmatch(r"(?:[0-9]+[smhd]|[0-9]{4}-[0-9]{2}-[0-9]{2}T[^ ]+)",since):return "Invalid --since value."
        args = ["docker", "logs", "--tail", str(max(1, min(lines, 1000)))]
        if since: args.extend(["--since", since[:30]])
        args.append(container)
        return self._run(args)

    def docker_inspect(self, container: str) -> str:
        """Inspect container metadata and state."""
        if not container or container.startswith("-"):return "Invalid container name."
        return self._run(["docker", "inspect", container])

    def docker_stats(self, container: str = "") -> str:
        """Show one-shot resource usage for all containers or one named container."""
        args=["docker","stats","--no-stream","--format","{{json .}}"]
        if container:
            if container.startswith("-"):return "Invalid container name."
            args.append(container)
        return self._run(args)

    def docker_manage(self, action: str, container: str) -> str:
        """Start, stop or restart a container; requires host mutation opt-in."""
        if action not in {"start","stop","restart"} or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}",container):return "Invalid Docker action/container."
        denied=self._mutate(f"docker {action}")
        if denied:return denied
        return self._run(["docker",action,container],timeout=90)

    def docker_exec(self, container: str, command: str) -> str:
        """Run a container command; arbitrary execution requires mutation opt-in."""
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}",container):return "Invalid container name."
        if not self.allow_mutations:
            return "docker exec is disabled. Set ADK_DEVIN_ALLOW_MUTATIONS=1 in the host environment to enable it."
        try: argv = shlex.split(command)
        except ValueError as exc: return f"Invalid command: {exc}"
        if not argv or len(argv) > 30: return "Invalid command."
        return self._run(["docker", "exec", container, *argv], timeout=90)

    # Devbox — commands run from the selected project root.
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

    # GitHub CLI: constrained action forms around gh, avoiding arbitrary shell strings.
    def gh_repo(self, repo: str = "") -> str:
        """Show GitHub repository metadata."""
        args = ["gh", "repo", "view"] + ([repo] if repo else []) + ["--json", "nameWithOwner,url,description,defaultBranchRef"]
        return self._run(args)

    def gh_issue_list(self, state: str = "open", limit: int = 20, repo: str = "") -> str:
        """List GitHub issues."""
        if state not in {"open", "closed", "all"}: return "Invalid issue state."
        args = ["gh", "issue", "list", "--state", state, "--limit", str(max(1, min(limit, 100))), "--json", "number,title,state,url"]
        if repo: args.extend(["--repo", repo])
        return self._run(args)

    def gh_issue_view(self, number: int, repo: str = "") -> str:
        """View a GitHub issue and its comments."""
        args = ["gh", "issue", "view", str(number), "--json", "number,title,body,state,comments,url"]
        if repo: args.extend(["--repo", repo])
        return self._run(args)

    def gh_issue_create(self, title: str, body: str, repo: str = "") -> str:
        """Create a GitHub issue; requires mutation opt-in."""
        denied = self._mutate("GitHub issue creation")
        if denied: return denied
        args = ["gh", "issue", "create", "--title", title[:250], "--body", body[:20_000]]
        if repo: args.extend(["--repo", repo])
        return self._run(args, timeout=90)

    def gh_pr_list(self, state: str = "open", limit: int = 20, repo: str = "") -> str:
        """List GitHub pull requests."""
        if state not in {"open", "closed", "merged", "all"}: return "Invalid PR state."
        args = ["gh", "pr", "list", "--state", state, "--limit", str(max(1, min(limit, 100))), "--json", "number,title,state,url,headRefName"]
        if repo: args.extend(["--repo", repo])
        return self._run(args)

    def gh_pr_checks(self, number: int = 0, repo: str = "") -> str:
        """Show CI checks for a pull request."""
        args = ["gh", "pr", "checks"]
        if number: args.append(str(number))
        if repo: args.extend(["--repo", repo])
        return self._run(args, timeout=90)

    def gh_pr_view(self, number: int, repo: str = "", diff: bool = False) -> str:
        """View a pull request and optionally include its diff."""
        args=["gh","pr","view",str(number),"--json","number,title,body,state,url,headRefName,baseRefName,comments"]
        if repo:args.extend(["--repo",repo])
        result=self._run(args)
        if diff:
            diff_args=["gh","pr","diff",str(number)]
            if repo:diff_args.extend(["--repo",repo])
            return result+"\\n"+self._run(diff_args)
        return result

    def gh_pr_create(self, title: str, body: str = "", base: str = "", head: str = "", draft: bool = False, repo: str = "") -> str:
        """Create a pull request; requires host mutation opt-in."""
        denied=self._mutate("GitHub pull request creation")
        if denied:return denied
        args=["gh","pr","create","--title",title[:250],"--body",body[:20000]]
        if base:args.extend(["--base",base])
        if head:args.extend(["--head",head])
        if draft:args.append("--draft")
        if repo:args.extend(["--repo",repo])
        return self._run(args,timeout=120)

    def gh_pr_comment(self, number: int, body: str, repo: str = "") -> str:
        """Comment on a pull request; requires host mutation opt-in."""
        denied=self._mutate("GitHub PR comment")
        if denied:return denied
        args=["gh","pr","comment",str(number),"--body",body[:20000]]
        if repo:args.extend(["--repo",repo])
        return self._run(args)

    def gh_pr_merge(self, number: int, method: str = "squash", repo: str = "") -> str:
        """Merge a pull request; requires host mutation opt-in."""
        denied=self._mutate("GitHub PR merge")
        if denied:return denied
        if method not in {"squash","merge","rebase"}:return "Invalid merge method."
        args=["gh","pr","merge",str(number),f"--{method}"]
        if repo:args.extend(["--repo",repo])
        return self._run(args,timeout=120)

    def gh_issue_comment(self, number: int, body: str, repo: str = "") -> str:
        """Comment on an issue; requires host mutation opt-in."""
        denied=self._mutate("GitHub issue comment")
        if denied:return denied
        args=["gh","issue","comment",str(number),"--body",body[:20000]]
        if repo:args.extend(["--repo",repo])
        return self._run(args)

    def gh_issue_close(self, number: int, comment: str = "", repo: str = "") -> str:
        """Close an issue; requires host mutation opt-in."""
        denied=self._mutate("GitHub issue close")
        if denied:return denied
        args=["gh","issue","close",str(number)]
        if comment:args.extend(["--comment",comment[:10000]])
        if repo:args.extend(["--repo",repo])
        return self._run(args)

    def gh_run_view(self, run_id: str, log: bool = False, repo: str = "") -> str:
        """Inspect a workflow run and optionally include failure logs."""
        if not re.fullmatch(r"[0-9]{1,20}",run_id):return "Invalid workflow run id."
        args=["gh","run","view",run_id]
        if log:args.append("--log-failed")
        if repo:args.extend(["--repo",repo])
        return self._run(args,timeout=120)

    def gh_release_list(self, repo: str = "") -> str:
        """List repository releases."""
        args=["gh","release","list","--limit","30"]
        if repo:args.extend(["--repo",repo])
        return self._run(args)

    def gh_api(self, endpoint: str, method: str = "GET", fields: dict[str,str] | None = None) -> str:
        """Call GitHub REST API; writes are host-gated and endpoint/fields are constrained."""
        method=method.upper()
        if method not in {"GET","POST","PATCH","PUT","DELETE"}:return "Unsupported HTTP method."
        if not re.fullmatch(r"[A-Za-z0-9_./-]{1,300}",endpoint) or endpoint.startswith("-") or ".." in endpoint:return "Invalid API endpoint."
        if method!="GET":
            denied=self._mutate(f"GitHub API {method}")
            if denied:return denied
        args=["gh","api",endpoint,"--method",method]
        for key,value in list((fields or {}).items())[:20]:
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}",key):return "Invalid field name."
            args.extend(["-f",f"{key}={value[:4000]}"])
        return self._run(args,timeout=90)

    def gh_run_list(self, limit: int = 10, repo: str = "") -> str:
        """List recent GitHub Actions workflow runs."""
        args = ["gh", "run", "list", "--limit", str(max(1, min(limit, 100))), "--json", "databaseId,displayTitle,status,conclusion,headBranch,url"]
        if repo: args.extend(["--repo", repo])
        return self._run(args)

    # Dependency tooling — delegated to pi-deps-equivalent ecosystem CLIs.
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
