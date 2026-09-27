"""ADK-native child-agent delegation, replacing pi-subagents' agent-tool pattern."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from google.adk.agents import LlmAgent
from google.adk.tools.agent_tool import AgentTool

from ..model import DevinLocal
from . import build_tools

DEFAULT_ROLES = {
    "researcher": "Investigate the assigned question. Use read-only project tools, cite files and report concise findings; do not modify files.",
    "reviewer": "Review the assigned code or plan for correctness, regressions, security and missing tests. Do not modify files.",
    "implementer": "Implement the assigned task in the configured workspace, run relevant tests, and summarize changed files and verification.",
}


def build_subagent_tools(workspace: str | Path, model_uid: str, roles: dict[str, str] | None = None) -> list[Any]:
    """Create ADK AgentTool delegates (researcher/reviewer/implementer by default).

    These are ADK-managed sub-agent handoffs, not detached resumable Pi child
    processes. The implementer gets file tools; read-only roles do not.
    """
    definitions = roles or DEFAULT_ROLES
    result=[]
    for name, instruction in definitions.items():
        writable = name == "implementer"
        groups = ["files", "web", "codegraph", "memory", "wiki"]
        if writable: groups += ["git", "devbox", "deps"]
        child=LlmAgent(name=f"devin_{name}", model=DevinLocal(model=model_uid),
            description=f"Delegate a {name} task to a Devin Local child agent.",
            instruction=instruction, tools=build_tools(workspace, groups))
        result.append(AgentTool(agent=child))
    return result
