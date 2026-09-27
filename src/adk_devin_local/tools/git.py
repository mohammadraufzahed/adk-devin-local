"""Pi-plugin-compatible ADK tool module."""
from __future__ import annotations

import json
from pathlib import Path
from .cli import CliTools

class GitTools(CliTools):
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
        if path:
            if Path(path).is_absolute() or ".." in Path(path).parts:return "Rejected path outside workspace."
            ref = f"{ref}:{path}"
        return self._run(["git", "show", ref])

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
