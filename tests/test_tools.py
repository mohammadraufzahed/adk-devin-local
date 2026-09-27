import json
import subprocess
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
from adk_devin_local.tools.git import GitTools
from adk_devin_local.tools.memory import MemoryTools
from adk_devin_local.tools.cron import CronTools
from adk_devin_local.tools.wiki import WikiTools
from adk_devin_local.tools.blackboard import BlackboardTools


def test_all_tool_groups_build_and_names_are_unique(tmp_path):
    funcs = build_tools(tmp_path)
    names = [fn.__name__ for fn in funcs]
    assert len(names) == sum(len(group) for group in GROUPS.values())
    assert len(names) == len(set(names))
    assert {"read_file", "create_file", "edit_file", "delete_file", "tg_send", "cron_add", "codegraph_context", "bb_set", "team_task"} <= set(names)


def test_tool_functions_are_accepted_by_adk_agent(tmp_path):
    agent = LlmAgent(name="test_agent", model=DevinLocal(model="swe-2-high"), tools=build_tools(tmp_path, ["files", "pi-websearch"]))
    assert agent.tools


def test_child_agents_are_adk_tools(tmp_path):
    children=build_subagent_tools(tmp_path,"swe-2-high")
    assert len(children)==3
    agent=LlmAgent(name="parent",model=DevinLocal(model="swe-2-high"),tools=children)
    assert agent.tools


def test_git_show_file_path(tmp_path):
    def git(*args):
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)

    git("init", "-q")
    git("config", "user.email", "test@example.invalid")
    git("config", "user.name", "Test")
    (tmp_path / "sample.txt").write_text("git show path works")
    git("add", "sample.txt")
    git("commit", "-qm", "fixture")
    result = json.loads(GitTools(tmp_path).git_show("HEAD", "sample.txt"))
    assert result["exit_code"] == 0
    assert result["output"] == "git show path works"


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


def test_plugin_specific_stateful_tools(tmp_path):
    memory = MemoryTools(tmp_path)
    cron = CronTools(tmp_path)
    wiki = WikiTools(tmp_path)
    blackboard = BlackboardTools(tmp_path)
    assert memory.memory_store("remember the deployment window", "ops").startswith("Stored")
    assert memory.memory_recall("deployment")[0]["key"] == "ops"
    assert cron.cron_add("every:15m", "check status").startswith("Recorded")
    assert len(cron.cron_list()) == 1
    assert cron.cron_list()[0]["spec"] == "every:15m"
    wiki.wiki_write("Runbook", "restart notes")
    assert "restart notes" in wiki.wiki_read("Runbook")
    blackboard.bb_set("state:deploy", "ready")
    assert blackboard.bb_get("state:deploy") == "ready"


def test_scheduler_library_validates_and_previews_cron_jobs(tmp_path):
    cron = CronTools(tmp_path)
    assert cron.cron_add("cron:*/5 * * * *", "poll").startswith("Recorded")
    assert cron.cron_list()[0]["next_run"]
    assert "Invalid cron expression" in cron.cron_add("cron:61 * * * *", "invalid")


def test_pi_plugin_groups_map_to_matching_modules(tmp_path):
    from adk_devin_local.tools import git, docker, devbox, gh, deps
    from adk_devin_local.tools import codegraph, websearch, webwatch, memory
    from adk_devin_local.tools import wiki, blackboard, project, cron, team
    from adk_devin_local.tools import telegram, voice, jev, subagents
    modules = [git, docker, devbox, gh, deps, codegraph, websearch, webwatch, memory,
               wiki, blackboard, project, cron, team, telegram, voice, jev, subagents]
    assert len(modules) == 18
    expected_groups = {"files", *(f"pi-{name}" for name in (
        "git", "docker", "devbox", "gh", "deps", "codegraph", "websearch", "webwatch",
        "memory", "wiki", "blackboard", "project", "cron", "team", "telegram", "voice",
        "jev", "subagents"))}
    assert set(GROUPS) == expected_groups
    import inspect
    for group, funcs in ((group, build_tools(tmp_path, [group])) for group in GROUPS):
        if not funcs or group == "files":
            continue
        expected_module = f"adk_devin_local.tools.{group.removeprefix('pi-')}"
        assert all(inspect.getmodule(func).__name__ == expected_module for func in funcs)


@pytest.mark.asyncio
async def test_webwatch_uses_feedparser(monkeypatch, tmp_path):
    from types import SimpleNamespace
    from adk_devin_local.tools import webwatch
    from adk_devin_local.tools.webwatch import WebwatchTools

    class FakeClient:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *_args):
            return None
        async def get(self, _url):
            return SimpleNamespace(content=b"<rss version='2.0'><channel><item><title>Entry</title><link>https://example.com/entry</link></item></channel></rss>", raise_for_status=lambda: None)

    monkeypatch.setattr(webwatch.httpx, "AsyncClient", lambda **_kwargs: FakeClient())
    monkeypatch.setattr(webwatch, "_public_url", lambda url: url)
    tools = WebwatchTools(tmp_path)
    tools._save("feeds.json", [{"url": "https://example.com/feed.xml", "name": "Example"}])
    items = await tools.webwatch_check()
    assert items == [{"feed": "Example", "title": "Entry", "link": "https://example.com/entry"}]


@pytest.mark.asyncio
async def test_telegram_tool_methods_dispatch_to_library_client(monkeypatch):
    from adk_devin_local.tools.telegram import TelegramTools

    tools = TelegramTools()
    tools.allow_mutations = True
    tools.chat = "123"
    calls = []

    async def fake_call(method, payload, **kwargs):
        calls.append((method, payload, kwargs))
        return {"ok": True}

    monkeypatch.setattr(tools, "_tg", fake_call)
    assert (await tools.tg_send("hello"))["ok"]
    assert (await tools.tg_react(1, "👍"))["ok"]
    assert (await tools.tg_pin(1))["ok"]
    assert (await tools.tg_edit(1, "updated"))["ok"]
    assert (await tools.tg_delete(1))["ok"]
    assert (await tools.tg_unpin())["ok"]
    assert [method for method, _, _ in calls] == [
        "sendMessage", "setMessageReaction", "pinChatMessage",
        "editMessageText", "deleteMessage", "unpinChatMessage",
    ]


@pytest.mark.asyncio
async def test_voice_transcription_uses_async_openai_client(monkeypatch):
    from types import SimpleNamespace
    from adk_devin_local.tools import voice
    from adk_devin_local.tools.voice import VoiceTools

    class FakeTranscriptions:
        async def create(self, **kwargs):
            assert kwargs["model"] == "whisper-1"
            assert kwargs["file"][0] == "clip.wav"
            return SimpleNamespace(text="transcribed")

    class FakeClient:
        def __init__(self, **kwargs):
            assert kwargs["api_key"] == "test-key"
            self.audio = SimpleNamespace(transcriptions=FakeTranscriptions())
        async def __aenter__(self): return self
        async def __aexit__(self, *_args): return None

    tools = VoiceTools()
    async def file_data(_file_id): return ("clip.wav", b"audio")
    monkeypatch.setattr(tools, "_telegram_file", file_data)
    monkeypatch.setattr(voice, "AsyncOpenAI", FakeClient)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    assert await tools.tg_transcribe("file-id") == {"text": "transcribed"}


@pytest.mark.asyncio
async def test_jev_choice_service_with_mocked_endpoint(monkeypatch):
    from adk_devin_local.tools import jev
    from adk_devin_local.tools.jev import JevTools

    class FakeResponse:
        def raise_for_status(self): pass
        def json(self): return {"answers": {"pick": {"choice": "item_2", "confidence": 0.9}}}

    class FakeClient:
        async def __aenter__(self): return self
        async def __aexit__(self, *_args): return None
        async def post(self, *args, **kwargs): return FakeResponse()

    monkeypatch.setattr(jev.httpx, "AsyncClient", lambda **_kwargs: FakeClient())
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    assert (await JevTools().jev_pick("best", ["a", "b"]))["picked"] == "b"


@pytest.mark.asyncio
async def test_telegram_api_uses_typed_library_client(monkeypatch):
    from adk_devin_local.tools.telegram import TelegramTools

    from types import SimpleNamespace

    class FakeBot:
        async def initialize(self):
            pass
        async def shutdown(self):
            pass
        async def send_message(self, **kwargs):
            return SimpleNamespace(to_dict=lambda: kwargs)

    tools = TelegramTools()
    tools.token = "test-token"
    monkeypatch.setattr(tools, "_bot", lambda: FakeBot())
    assert await tools._tg("sendMessage", {"chat_id": "123", "text": "hello"}) == {
        "chat_id": "123", "text": "hello"
    }


@pytest.mark.asyncio
async def test_web_search_uses_ddgs(monkeypatch):
    from adk_devin_local.tools import websearch

    class FakeDDGS:
        def text(self, query, max_results):
            assert query == "pi plugins"
            assert max_results == 10
            return [{"title": "Result", "href": "https://example.com", "body": "Snippet"}]

    monkeypatch.setattr(websearch, "DDGS", FakeDDGS)
    assert await websearch.web_search("pi plugins", limit=20) == [
        {"title": "Result", "url": "https://example.com", "snippet": "Snippet"}
    ]


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
