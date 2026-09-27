"""Composable ADK tools porting the capabilities of the author's Pi plugins.

Tools are returned as ordinary Python callables, as supported by ADK LlmAgent.
Only expose groups an application intends to grant; write-capable commands have
additional host-environment gates.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .cli import CliTools
from .codegraph import CodeGraphTools
from .files import FileTools
from .integrations import IntegrationTools
from .stateful import StatefulTools
from .web import web_fetch, web_search

GROUPS: dict[str, tuple[str, ...]] = {
    "files": ("read_file", "create_file", "write_file", "edit_file", "list_files", "search_files", "delete_file", "move_file"),
    "git": ("git_status", "git_diff", "git_log", "git_blame", "git_branches", "git_file_history"),
    "docker": ("docker_ps", "docker_logs", "docker_stats", "docker_inspect", "docker_exec"),
    "devbox": ("devbox_info", "devbox_config", "devbox_run", "devbox_services", "devbox_search", "devbox_script", "devbox_env", "devbox_generate", "devbox_update", "devbox_package", "devbox_init"),
    "github": ("gh_repo", "gh_issue_list", "gh_issue_view", "gh_issue_create", "gh_issue_comment", "gh_issue_close", "gh_pr_list", "gh_pr_view", "gh_pr_create", "gh_pr_comment", "gh_pr_merge", "gh_pr_checks", "gh_run_list", "gh_run_view", "gh_release_list", "gh_api"),
    "deps": ("deps_audit", "deps_outdated", "deps_licenses", "deps_update"),
    "codegraph": ("codegraph_status", "codegraph_init", "codegraph_sync", "codegraph_query", "codegraph_context", "codegraph_explore", "codegraph_node", "codegraph_files"),
    "web": ("web_search", "web_fetch"),
    "webwatch": ("webwatch_add", "webwatch_list", "webwatch_check", "webwatch_remove"),
    "memory": ("memory_store", "memory_recall", "memory_forget"),
    "wiki": ("wiki_write", "wiki_read", "wiki_search"),
    "blackboard": ("bb_set", "bb_get", "bb_append", "bb_list", "bb_claim"),
    "project": ("project_list", "project_current", "project_use", "project_register", "project_forget"),
    "cron": ("cron_add", "cron_list", "cron_pause", "cron_edit", "cron_remove"),
    "team": ("team_roster", "team_ask", "team_task", "team_emit", "team_handoff", "team_say", "team_status"),
    "telegram": ("tg_send", "tg_react", "tg_pin", "tg_edit", "tg_delete", "tg_unpin", "tg_history"),
    "voice": ("tg_voice", "tg_transcribe"),
    "jev": ("jev_decide", "jev_pick"),
}


def build_tools(workspace: str | Path, groups: list[str] | tuple[str, ...] | None = None) -> list[Any]:
    """Build ADK-callable tool functions rooted at ``workspace``.

    ``groups=None`` enables all groups; preferably pass an explicit list. Groups
    are: files, git, docker, devbox, github, deps, codegraph, web, webwatch,
    memory, wiki, blackboard, project, cron, team, telegram, voice, jev.

    Set ADK_DEVIN_ALLOW_MUTATIONS=1 in the trusted host environment to enable
    gated operations such as commits, package updates, container exec and
    arbitrary Devbox commands. The model cannot override this host setting.
    """
    selected = tuple(groups or GROUPS.keys())
    unknown = set(selected) - set(GROUPS)
    if unknown:
        raise ValueError(f"Unknown tool groups: {', '.join(sorted(unknown))}")
    root = Path(workspace).expanduser().resolve(strict=True)
    instances: dict[str, Any] = {
        "files": FileTools(root), "git": CliTools(root), "docker": None,
        "devbox": None, "github": None, "deps": None, "codegraph": CodeGraphTools(root),
        "webwatch": StatefulTools(root), "memory": None, "wiki": None,
        "blackboard": None, "project": None, "cron": None, "team": None,
        "telegram": IntegrationTools(), "voice": None, "jev": None,
        "web": None,
    }
    cli = instances["git"]
    for group in ("git", "docker", "devbox", "github", "deps"):
        instances[group] = cli
    integrations = instances["telegram"]
    instances["voice"] = integrations
    instances["jev"] = integrations
    local = instances["webwatch"]
    for group in ("memory", "wiki", "blackboard", "project", "cron", "team"):
        instances[group] = local
    web = type("WebTools", (), {"web_search": staticmethod(web_search), "web_fetch": staticmethod(web_fetch)})()
    instances["web"] = web
    return [getattr(instances[group], name) for group in selected for name in GROUPS[group]]


__all__ = ["GROUPS", "build_tools"]
