import json

import pytest
from google.adk.agents import LlmAgent
from google.adk.models.llm_request import LlmRequest
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from adk_devin_local import DevinLocal, build_tools


@pytest.mark.asyncio
async def test_model_streaming_and_function_call(monkeypatch):
    async def fake_generate(model, system, contents, tools, max_tokens):
        assert max_tokens == 128_000
        assert model == "swe-2-high"
        assert system == "instruction"
        yield "text", "hi"
        yield "tool_start", ("call-1", "lookup")
        # The private stream omits the call id from argument deltas.
        yield "tool_args", (None, '{"q":"x"}')
        yield "usage", {"input_tokens": 3, "output_tokens": 2}
        yield "finish", "tool_calls"

    monkeypatch.setattr("adk_devin_local.model.generate", fake_generate)
    model = DevinLocal(model="swe-2-high")
    request = LlmRequest(
        model="swe-2-high",
        contents=[types.Content(role="user", parts=[types.Part(text="go")])],
        config=types.GenerateContentConfig(system_instruction="instruction"),
    )
    responses = [r async for r in model.generate_content_async(request, stream=True)]
    assert responses[0].partial is True
    final = responses[-1]
    assert final.partial is False
    assert final.content.parts[0].text == "hi"
    assert final.content.parts[1].function_call.name == "lookup"
    assert final.content.parts[1].function_call.args == {"q": "x"}
    assert final.usage_metadata.total_token_count == 5


@pytest.mark.asyncio
async def test_model_rejects_tool_arguments_without_a_matching_call(monkeypatch):
    async def fake_generate(*args):
        yield "tool_args", (None, '{"q":"x"}')

    monkeypatch.setattr("adk_devin_local.model.generate", fake_generate)
    model = DevinLocal(model="swe-2-high")
    request = LlmRequest(model="swe-2-high")

    with pytest.raises(RuntimeError, match="without a matching call"):
        _ = [response async for response in model.generate_content_async(request)]


@pytest.mark.asyncio
async def test_model_nonstream_returns_completed_response(monkeypatch):
    async def fake_generate(*args):
        yield "text", "answer"
        yield "finish", "stop"

    monkeypatch.setattr("adk_devin_local.model.generate", fake_generate)
    model = DevinLocal(model="swe-2-high")
    request = LlmRequest(model="swe-2-high")
    responses = [r async for r in model.generate_content_async(request)]
    assert len(responses) == 1
    assert responses[0].content.parts[0].text == "answer"


@pytest.mark.asyncio
async def test_adk_runner_executes_tool_with_argument_deltas_without_call_id(
    monkeypatch, tmp_path
):
    (tmp_path / "fixture.txt").write_text("argument routing works")

    async def fake_generate(_model, _system, contents, _tools, _max_tokens):
        function_responses = [
            part.function_response
            for content in contents
            for part in content.parts or []
            if part.function_response
        ]
        if function_responses:
            yield "text", json.dumps(function_responses[-1].response)
            yield "finish", "stop"
            return

        yield "tool_start", ("call-1", "read_file")
        yield "tool_args", (None, '{"path":')
        yield "tool_args", (None, '"fixture.txt"}')
        yield "finish", "tool_calls"

    monkeypatch.setattr("adk_devin_local.model.generate", fake_generate)
    app_name = "idless-tool-arguments"
    user_id = "test-user"
    sessions = InMemorySessionService()
    session = await sessions.create_session(app_name=app_name, user_id=user_id)
    agent = LlmAgent(
        name="argument_test_agent",
        model=DevinLocal(model="fake"),
        tools=build_tools(tmp_path, ["files"]),
    )
    runner = Runner(agent=agent, app_name=app_name, session_service=sessions)

    answers = []
    async for event in runner.run_async(
        user_id=user_id,
        session_id=session.id,
        new_message=types.Content(
            role="user", parts=[types.Part(text="Read fixture.txt")]
        ),
    ):
        if event.content:
            answers.extend(part.text for part in event.content.parts or [] if part.text)

    assert any("argument routing works" in answer for answer in answers)
