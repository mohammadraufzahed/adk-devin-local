import gzip

import pytest

from adk_devin_local.wire import blob, connect_frame, connect_payloads, fields, text, uint, varint


def test_varint_and_nested_fields_round_trip():
    message = uint(1, 300) + text(2, "hello") + blob(3, b"\x00\xff")
    assert list(fields(message)) == [(1, 0, 300), (2, 2, b"hello"), (3, 2, b"\x00\xff")]
    assert varint(300) == b"\xac\x02"


def test_connect_gzip_frame_round_trip():
    frame = connect_frame(b"test payload")
    trailer = b"\x02" + len(b"{}").to_bytes(4, "big") + b"{}"
    assert list(connect_payloads(frame + trailer)) == [(False, b"test payload"), (True, b"{}")] 


def test_truncated_connect_frame_rejected():
    with pytest.raises(ValueError, match="truncated"):
        list(connect_payloads(b"\x01\x00"))
