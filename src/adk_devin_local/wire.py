"""Minimal protobuf and Connect framing helpers used by the experimental Devin adapter."""
from __future__ import annotations

import gzip
import struct
from collections.abc import Iterator


def varint(value: int) -> bytes:
    if value < 0:
        raise ValueError("protobuf varint must be non-negative")
    out = bytearray()
    while value > 0x7f:
        out.append((value & 0x7f) | 0x80)
        value >>= 7
    out.append(value)
    return bytes(out)


def tag(number: int, wire: int) -> bytes:
    return varint((number << 3) | wire)


def uint(number: int, value: int) -> bytes:
    return tag(number, 0) + varint(value)


def text(number: int, value: str) -> bytes:
    data = value.encode()
    return tag(number, 2) + varint(len(data)) + data


def blob(number: int, value: bytes) -> bytes:
    return tag(number, 2) + varint(len(value)) + value


def fixed64(number: int, value: float) -> bytes:
    return tag(number, 1) + struct.pack("<d", value)


def fields(data: bytes) -> Iterator[tuple[int, int, int | bytes]]:
    i = 0
    while i < len(data):
        t, i = read_varint(data, i)
        number, wire = t >> 3, t & 7
        if wire == 0:
            value, i = read_varint(data, i)
            yield number, wire, value
        elif wire == 1:
            if i + 8 > len(data): raise ValueError("truncated fixed64")
            yield number, wire, data[i:i+8]; i += 8
        elif wire == 2:
            size, i = read_varint(data, i)
            if size > len(data) - i: raise ValueError("truncated protobuf field")
            yield number, wire, data[i:i+size]; i += size
        elif wire == 5:
            if i + 4 > len(data): raise ValueError("truncated fixed32")
            yield number, wire, data[i:i+4]; i += 4
        else:
            raise ValueError(f"unsupported protobuf wire type {wire}")


def read_varint(data: bytes, offset: int) -> tuple[int, int]:
    value = shift = 0
    while offset < len(data):
        b = data[offset]; offset += 1
        value |= (b & 0x7f) << shift
        if b < 0x80: return value, offset
        shift += 7
        if shift > 70: break
    raise ValueError("invalid or truncated varint")


def connect_frame(payload: bytes) -> bytes:
    packed = gzip.compress(payload)
    return b"\x01" + struct.pack(">I", len(packed)) + packed


def connect_payloads(data: bytes) -> Iterator[tuple[bool, bytes]]:
    """Yield (is_trailer, payload) from Connect's length-prefixed response."""
    offset = 0
    while offset < len(data):
        if len(data) - offset < 5: raise ValueError("truncated Connect frame header")
        flags, length = data[offset], struct.unpack(">I", data[offset+1:offset+5])[0]
        offset += 5
        if length > len(data) - offset: raise ValueError("truncated Connect frame")
        chunk = data[offset:offset+length]; offset += length
        if flags & 1: chunk = gzip.decompress(chunk)
        yield bool(flags & 2), chunk
