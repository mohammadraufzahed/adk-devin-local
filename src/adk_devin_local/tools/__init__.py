"""ADK adapters, kept in one module per original Pi plugin.

The implementation module names mirror the upstream Personal projects:
``git.py`` is the adapter for ``pi-git``, ``docker.py`` for ``pi-docker``,
and so on. Only registration/group selection lives here.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .files import FileTools
from .blackboard import BlackboardTools
from .cognition import CognitionTools
from .codegraph import CodeGraphTools
from .cron import CronTools
from .deps import DependencyTools
from .devbox import DevboxTools
from .docker import DockerTools
from .gh import GithubTools
from .git import GitTools
from .jev import JevTools
from .memory import MemoryTools
from .project import ProjectTools
from .team import TeamTools
from .telegram import TelegramTools
from .voice import VoiceTools
from .websearch import web_fetch, web_search
from .webwatch import WebwatchTools
from .wiki import WikiTools

GROUPS: dict[str, tuple[str, ...]] = {
    "files": ("read_file", "create_file", "write_file", "edit_file", "list_files", "search_files", "delete_file", "move_file"),
    "pi-git": ("git_status", "git_diff", "git_log", "git_blame", "git_branches", "git_file_history"),
    "pi-docker": ("docker_ps", "docker_logs", "docker_stats", "docker_inspect", "docker_exec"),
    "pi-devbox": ("devbox_info", "devbox_config", "devbox_run", "devbox_services", "devbox_search", "devbox_script", "devbox_env", "devbox_generate", "devbox_update", "devbox_package", "devbox_add", "devbox_remove", "devbox_init"),
    "pi-gh": ("gh_repo", "gh_issue_list", "gh_issue_view", "gh_issue_create", "gh_issue_comment", "gh_issue_close", "gh_pr_list", "gh_pr_view", "gh_pr_diff", "gh_pr_review", "gh_pr_create", "gh_pr_comment", "gh_pr_merge", "gh_pr_checks", "gh_run_list", "gh_run_view", "gh_release_list", "gh_api", "gh_comment_react", "gh_comment_reply"),
    "pi-deps": ("deps_audit", "deps_outdated", "deps_licenses", "deps_update"),
    "pi-codegraph": ("codegraph_status", "codegraph_init", "codegraph_sync", "codegraph_query", "codegraph_context", "codegraph_explore", "codegraph_node", "codegraph_files"),
    "pi-websearch": ("web_search", "web_fetch"),
    "pi-webwatch": ("webwatch_add", "webwatch_list", "webwatch_check", "webwatch_remove"),
    "pi-memory": ("memory_store", "memory_recall", "memory_forget"),
    "pi-cognition": ("skill_save", "skill_list", "skill_read", "skill_forget", "recall_search", "user_note", "user_recall", "user_forget"),
    "pi-wiki": ("wiki_write", "wiki_read", "wiki_list", "wiki_search"),
    "pi-blackboard": ("bb_set", "bb_get", "bb_append", "bb_list", "bb_claim"),
    "pi-project": ("project_list", "project_current", "project_use", "project_register", "project_forget", "project_mode"),
    "pi-cron": ("cron_add", "cron_list", "cron_pause", "cron_edit", "cron_remove", "job_state"),
    "pi-team": ("team_roster", "team_ask", "team_task", "team_emit", "team_handoff", "team_say", "team_status"),
    "pi-telegram": ("tg_send", "tg_react", "tg_pin", "tg_edit", "tg_delete", "tg_unpin", "tg_history", "tg_topics"),
    "pi-voice": ("tg_voice", "tg_transcribe"),
    "pi-jev": ("jev_decide", "jev_pick"),
    # ADK child delegation is exposed separately by build_subagent_tools().
    "pi-subagents": (),
}


def _guarded(fn):
    """Return a wrapper that converts tool exceptions into error results.

    google-adk propagates exceptions raised inside a FunctionTool up
    through the node runner, killing the whole run. Returning an error
    string instead lets the model see the failure and retry.
    functools.wraps preserves the signature ADK inspects.
    """
    import functools
    import inspect

    def _err(exc: Exception):
        return {"error": f"{type(exc).__name__}: {exc}"[:500]}

    if inspect.iscoroutinefunction(fn):
        @functools.wraps(fn)
        async def awrapper(*args, **kwargs):
            try:
                return await fn(*args, **kwargs)
            except Exception as exc:  # never kill the run
                return _err(exc)
        return awrapper

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:  # never kill the run
            return _err(exc)
    return wrapper


def build_tools(workspace: str | Path, groups: list[str] | tuple[str, ...] | None = None, env: dict[str, str] | None = None) -> list[Any]:
    """Build ADK function tools, selecting original Pi plugin IDs.

    Pass e.g. ``groups=["pi-git", "pi-docker", "pi-gh"]``. ``groups=None``
    enables all tools. Plugin modules are separate files with matching names.

    ``ADK_DEVIN_ALLOW_MUTATIONS=1`` in the trusted host environment enables
    gated writes; the model cannot override this environment-level setting.
    """
    selected = tuple(GROUPS if groups is None else groups)
    unknown = set(selected) - set(GROUPS)
    if unknown:
        raise ValueError(f"Unknown plugin groups: {', '.join(sorted(unknown))}")
    root = Path(workspace).expanduser().resolve(strict=True)
    stateful = {
        name: factory(root, env=env)
        for name, factory in {
            "pi-blackboard": BlackboardTools,
            "pi-cognition": CognitionTools,
            "pi-cron": CronTools,
            "pi-memory": MemoryTools,
            "pi-project": ProjectTools,
            "pi-team": TeamTools,
            "pi-webwatch": WebwatchTools,
            "pi-wiki": WikiTools,
        }.items()
    }
    tools: dict[str, Any] = {
        "files": FileTools(root),
        "pi-git": GitTools(root, env=env),
        "pi-docker": DockerTools(root, env=env),
        "pi-devbox": DevboxTools(root, env=env),
        "pi-gh": GithubTools(root, env=env),
        "pi-deps": DependencyTools(root, env=env),
        "pi-codegraph": CodeGraphTools(root, env=env),
        "pi-websearch": type("WebSearchTools", (), {"web_search": staticmethod(web_search), "web_fetch": staticmethod(web_fetch)})(),
        "pi-telegram": TelegramTools(env=env),
        "pi-voice": VoiceTools(env=env),
        "pi-jev": JevTools(env=env),
        "pi-subagents": None,
        **stateful,
    }
    return [_guarded(getattr(tools[group], name)) for group in selected for name in GROUPS[group]]


__all__ = ["GROUPS", "build_tools"]
