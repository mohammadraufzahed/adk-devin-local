import json
from pathlib import Path

import pytest
from google.adk.agents import LlmAgent
from google.adk.models import BaseLlm
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from adk_devin_local import DevinLocal, GROUPS, build_tools, build_subagent_tools
from adk_devin_local.tools.files import FileTools
from adk_devin_local.tools.stateful import StatefulTools


def test_all_tool_groups_build_and_names_are_unique(tmp_path):
    funcs = build_tools(tmp_path)
    names = [fn.__name__ for fn in funcs]
    assert len(names) == sum(len(group) for group in GROUPS.values())
    assert len(names) == len(set(names))
    assert {"read_file", "create_file", "edit_file", "delete_file", "tg_send", "cron_add", "codegraph_context", "bb_set", "team_task"} <= set(names)


def test_tool_functions_are_accepted_by_adk_agent(tmp_path):
    agent = LlmAgent(name="test_agent", model=DevinLocal(model="swe-2-high"), tools=build_tools(tmp_path, ["files", "web"]))
    assert agent.tools


def test_child_agents_are_adk_tools(tmp_path):
    children=build_subagent_tools(tmp_path,"swe-2-high")
    assert len(children)==3
    agent=LlmAgent(name="parent",model=DevinLocal(model="swe-2-high"),tools=children)
    assert agent.tools


def test_file_operations_and_root_confinement(tmp_path):
    files = FileTools(tmp_path)
    files.create_file("src/example.py", "value = 1\n")
    assert files.read_file("src/example.py") == "value = 1\n"
    files.edit_file("src/example.py", "value = 1", "value = 2")
    assert "value = 2" in files.read_file("src/example.py")
    assert files.list_files("src") == ["src/example.py"]
    with pytest.raises(ValueError, match="exactly one"):
        files.edit_file("src/example.py", "missing", "x")
    with pytest.raises(ValueError, match="escapes"):
        files.read_file("../outside.txt")
    with pytest.raises(ValueError, match="confirm=true"):
        files.delete_file("src/example.py")
    files.delete_file("src/example.py", confirm=True)
    assert not (tmp_path / "src/example.py").exists()


def test_file_tools_reject_symlink_escape(tmp_path):
    outside = tmp_path.parent / "outside-adk-test.txt"
    outside.write_text("secret")
    (tmp_path / "escape").symlink_to(outside)
    with pytest.raises(ValueError, match="escapes"):
        FileTools(tmp_path).read_file("escape")
    outside.unlink()


def test_stateful_memory_cron_wiki_and_blackboard(tmp_path):
    state = StatefulTools(tmp_path)
    assert state.memory_store("remember the deployment window", "ops").startswith("Stored")
    assert state.memory_recall("deployment")[0]["key"] == "ops"
    assert state.cron_add("every:15m", "check status").startswith("Recorded")
    assert len(state.cron_list()) == 1
    assert state.cron_list()[0]["spec"] == "every:15m"
    state.wiki_write("Runbook", "restart notes")
    assert "restart notes" in state.wiki_read("Runbook")
    state.blackboard_set("state:deploy", "ready")
    assert state.blackboard_get("state:deploy") == "ready"


class _FakeToolModel(BaseLlm):
    model: str = "fake"

    async def generate_content_async(self, llm_request: LlmRequest, stream: bool = False):
        for content in llm_request.contents:
            for part in content.parts or []:
                if part.function_response:
                    answer=json.dumps(part.function_response.response)
                    yield LlmResponse(content=types.Content(role="model",parts=[types.Part(text=answer)]))
                    return
        yield LlmResponse(content=types.Content(role="model",parts=[types.Part(function_call=types.FunctionCall(name="read_file",args={"path":"fixture.txt"}))]))


@pytest.mark.asyncio
async def test_adk_executes_file_tool_and_returns_tool_result(tmp_path):
    (tmp_path/"fixture.txt").write_text("tool cycle success")
    app="file-tool-test"; user="test-user"
    sessions=InMemorySessionService()
    session=await sessions.create_session(app_name=app,user_id=user)
    agent=LlmAgent(name="file_tool_agent",model=_FakeToolModel(model="fake"),tools=build_tools(tmp_path,["files"]))
    runner=Runner(agent=agent,app_name=app,session_service=sessions)
    answers=[]
    async for event in runner.run_async(user_id=user,session_id=session.id,new_message=types.Content(role="user",parts=[types.Part(text="Read fixture.txt")])):
        if event.content:
            answers.extend(part.text for part in (event.content.parts or []) if part.text)
    assert any("tool cycle success" in answer for answer in answers)
