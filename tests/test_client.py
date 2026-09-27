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
