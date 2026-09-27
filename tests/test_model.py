import pytest
from google.adk.models.llm_request import LlmRequest
from google.genai import types

from adk_devin_local import DevinLocal


@pytest.mark.asyncio
async def test_model_streaming_and_function_call(monkeypatch):
    async def fake_generate(model, system, contents, tools, max_tokens):
        assert max_tokens == 128_000
        assert model == "swe-2-high"
        assert system == "instruction"
        yield "text", "hi"
        yield "tool_start", ("call-1", "lookup")
        yield "tool_args", ("call-1", '{"q":"x"}')
        yield "usage", {"input_tokens": 3, "output_tokens": 2}
        yield "finish", "tool_calls"

    monkeypatch.setattr("adk_devin_local.model.generate", fake_generate)
    model = DevinLocal(model="swe-2-high")
    request = LlmRequest(model="swe-2-high", contents=[types.Content(role="user", parts=[types.Part(text="go")])],
                         config=types.GenerateContentConfig(system_instruction="instruction"))
    responses = [r async for r in model.generate_content_async(request, stream=True)]
    assert responses[0].partial is True
    final = responses[-1]
    assert final.partial is False
    assert final.content.parts[0].text == "hi"
    assert final.content.parts[1].function_call.name == "lookup"
    assert final.content.parts[1].function_call.args == {"q": "x"}
    assert final.usage_metadata.total_token_count == 5


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
