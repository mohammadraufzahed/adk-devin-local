from adk_devin_local.client import _decode_chat_frame, _metadata, _request
from adk_devin_local.wire import blob, fields, text


def test_metadata_includes_cli_style_client_identity_and_jwt():
    encoded = _metadata("fake-key", "session", "trigger", 42, "eyJ.fake")
    values = {n: v for n, w, v in fields(encoded) if w == 2 and isinstance(v, bytes)}
    assert values[1] == b"devin-desktop"
    assert values[3] == b"fake-key"
    assert values[21] == b"eyJ.fake"


def test_request_places_system_prompt_in_system_slot():
    request = _request(
        "swe-2-high", "key", "jwt", "system instructions", [], [], "session"
    )
    text_fields = [
        (n, v.decode()) for n, w, v in fields(request) if n in (2, 21) and w == 2
    ]
    assert (2, "system instructions") in text_fields
    assert (21, "swe-2-high") in text_fields


def test_decode_chat_text_and_finish_frames():
    from adk_devin_local.wire import uint

    frame = text(3, "hello") + uint(5, 10)
    assert _decode_chat_frame(frame) == [("text", "hello"), ("finish", "tool_calls")]


def test_decode_tool_argument_delta_without_call_id():
    start = blob(
        6,
        text(1, "call-1") + text(2, "lookup") + text(3, '{"q":'),
    )
    continuation = blob(6, text(3, '"x"}'))

    assert _decode_chat_frame(start) == [
        ("tool_start", ("call-1", "lookup")),
        ("tool_args", ("call-1", '{"q":')),
    ]
    assert _decode_chat_frame(continuation) == [("tool_args", (None, '"x"}'))]


def test_pack_tool_uses_parameters_json_schema_when_parameters_is_none():
    """google-adk>=2.9 sets parameters_json_schema, leaving parameters=None."""
    import json as _json
    from google.genai import types
    from adk_devin_local.client import _pack_tool

    schema = {
        "type": "object",
        "properties": {"number": {"type": "integer"}},
        "required": ["number"],
    }
    fn = types.FunctionDeclaration(
        name="gh_issue_view",
        description="View an issue",
        parameters_json_schema=schema,
    )
    tool = types.Tool(function_declarations=[fn])
    packed = _pack_tool(tool)
    blobs = [v for n, w, v in fields(packed) if n == 10 and isinstance(v, bytes)]
    assert blobs, "expected one packed function declaration"
    inner = {n: v for n, w, v in fields(blobs[0]) if w == 2}
    assert inner[1].decode() == "gh_issue_view"
    sent = _json.loads(inner[3].decode())
    assert sent["required"] == ["number"]
    assert "number" in sent["properties"]


def test_pack_tool_prefers_parameters_over_json_schema():
    import json as _json
    from google.genai import types
    from adk_devin_local.client import _pack_tool

    schema = types.Schema(
        type="OBJECT", properties={"x": types.Schema(type="STRING")}, required=["x"]
    )
    fn = types.FunctionDeclaration(
        name="f", description="d", parameters=schema,
        parameters_json_schema={"type": "object", "properties": {}},
    )
    packed = _pack_tool(types.Tool(function_declarations=[fn]))
    blobs = [v for n, w, v in fields(packed) if n == 10 and isinstance(v, bytes)]
    inner = {n: v for n, w, v in fields(blobs[0]) if w == 2}
    sent = _json.loads(inner[3].decode())
    assert "x" in sent.get("properties", {})


def test_pack_content_emits_one_message_per_function_response():
    """Parallel tool calls → N function_response parts → N messages, each
    tagged with its own call id (field 7). Previously only the last
    survived, which misattributed outputs."""
    from google.genai import types
    from adk_devin_local.client import _pack_content

    content = types.Content(
        role="tool",
        parts=[
            types.Part(function_response=types.FunctionResponse(
                id="call-1", name="a", response={"result": "first"})),
            types.Part(function_response=types.FunctionResponse(
                id="call-2", name="b", response={"result": "second"})),
        ],
    )
    messages = _pack_content(content)
    assert len(messages) == 2
    seen = []
    for msg in messages:
        inner = [v for n, w, v in fields(msg) if n == 3][0]
        inner_fields = {n: v for n, w, v in fields(inner)}
        assert inner_fields[2] == 4  # source varint = tool result
        seen.append((inner_fields[7].decode(), inner_fields[3].decode()))
    assert ("call-1", '{"result": "first"}') in seen
    assert ("call-2", '{"result": "second"}') in seen
