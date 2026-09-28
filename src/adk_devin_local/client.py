"""Experimental client for Devin Local's private Connect/protobuf model endpoint.

This intentionally mirrors the protocol used by pi-devin-local. Cognition does
not document or guarantee this endpoint; treat compatibility as best-effort.
"""
from __future__ import annotations

import base64
import json
import os
import platform
import random
import struct
import time
import tomllib
import uuid
from pathlib import Path
from typing import Any, AsyncIterator

import httpx

from .wire import blob, connect_frame, connect_payloads, fields, fixed64, text, uint

DEFAULT_HOST = "https://server.codeium.com"


def credentials() -> tuple[str, str]:
    """Return Devin CLI API key and API server without printing credential data."""
    path = Path(os.environ.get("DEVIN_CREDENTIALS", Path.home() / ".local/share/devin/credentials.toml"))
    if not path.is_file():
        raise RuntimeError(f"Devin CLI credentials not found at {path}; run `devin auth login` first")
    with path.open("rb") as stream:
        values = tomllib.load(stream)
    key = values.get("windsurf_api_key")
    if not isinstance(key, str) or not key:
        raise RuntimeError("No Devin Local API credential found; sign in with the Devin CLI")
    host = os.environ.get("DEVIN_API_SERVER_URL") or values.get("api_server_url") or DEFAULT_HOST
    return key, str(host).rstrip("/")


def _metadata(key: str, session: str, trigger: str, request_id: int, jwt: str | None = None) -> bytes:
    version = os.environ.get("DEVIN_CLIENT_VERSION", "3.6.27")
    ide = "devin-desktop"
    os_name = {"Darwin": "darwin", "Windows": "windows"}.get(platform.system(), "linux")
    now = time.time()
    timestamp = uint(1, int(now)) + uint(2, int((now % 1) * 1_000_000_000))
    out = b"".join((text(1, ide), text(2, version), text(3, key), text(4, "en"),
        text(5, os_name), text(7, version), uint(9, request_id), text(10, session),
        text(12, ide), blob(16, timestamp), text(25, trigger), text(26, "Unset"), text(28, ide)))
    if jwt: out += text(21, jwt)
    return out


async def _user_jwt(client: httpx.AsyncClient, key: str, host: str) -> str:
    sid, trigger = str(uuid.uuid4()), str(uuid.uuid4())
    response = await client.post(f"{host}/exa.auth_pb.AuthService/GetUserJwt",
        headers={"Content-Type": "application/proto", "Connect-Protocol-Version": "1"},
        content=blob(1, _metadata(key, sid, trigger, int(time.time() * 1000))))
    response.raise_for_status()
    for number, wire, value in fields(response.content):
        if number == 1 and wire == 2 and isinstance(value, bytes):
            token = value.decode(errors="ignore")
            if token.startswith("eyJ"): return token
    raise RuntimeError("Devin GetUserJwt response did not contain a JWT")


def _pack_tool(tool: Any) -> bytes:
    declaration = getattr(tool, "function_declarations", None)
    if not declaration: return b""
    chunks = []
    for fn in declaration:
        if fn.parameters:
            parameters = fn.parameters.model_dump(exclude_none=True, by_alias=True)
        elif getattr(fn, "parameters_json_schema", None):
            # google-adk >= 2.9 populates parameters_json_schema instead of
            # parameters when JSON_SCHEMA_FOR_FUNC_DECL is enabled.
            parameters = fn.parameters_json_schema
        else:
            parameters = {}
        chunks.append(blob(10, text(1, fn.name or "") + text(2, fn.description or "") + text(3, json.dumps(parameters))))
    return b"".join(chunks)


def _pack_content(content: Any) -> list[bytes]:
    role = getattr(content, "role", "user") or "user"
    source = {"user": 1, "model": 2, "assistant": 2, "function": 4}.get(role, 1)
    text_chunks: list[str] = []
    image_fields: list[bytes] = []
    tool_calls: list[bytes] = []
    tool_results: list[tuple[str, str]] = []  # (call_id, response_json)
    for part in getattr(content, "parts", None) or []:
        if part.text:
            text_chunks.append(part.text)
        if part.inline_data and part.inline_data.data:
            img = text(1, base64.b64encode(part.inline_data.data).decode()) + text(2, part.inline_data.mime_type or "image/png")
            image_fields.append(blob(10, img))
        if part.function_call:
            fc = part.function_call
            tool_calls.append(blob(6, text(1, fc.id or str(uuid.uuid4())) + text(2, fc.name or "") + text(3, json.dumps(fc.args or {}))))
        if part.function_response:
            fr = part.function_response
            tool_results.append((fr.id or fr.name or "", json.dumps(fr.response or {})))
    # Parallel tool calls produce multiple function_response parts in one
    # Content — the wire protocol carries one result per message (field 7),
    # so emit a separate message per response. Without this every result
    # except the last was silently dropped (outputs looked "swapped").
    if tool_results:
        messages = []
        for call_id, result in tool_results:
            body = uint(2, 4) + text(3, result) + uint(4, max(1, len(result) // 4)) + uint(5, 1)
            if call_id: body += text(7, call_id)
            messages.append(blob(3, body))
        return messages
    body = uint(2, source) + text(3, "\n".join(text_chunks)) + uint(4, max(1, len("\n".join(text_chunks)) // 4)) + uint(5, 1)
    return [blob(3, body + b"".join(tool_calls) + b"".join(image_fields))]


def _request(model_uid: str, key: str, jwt: str, system: str, contents: list[Any], tools: list[Any], session: str, max_tokens: int = 128_000) -> bytes:
    cascade, trajectory, trigger = (str(uuid.uuid4()) for _ in range(3))
    metadata = _metadata(key, session, trigger, int(time.time() * 1000), jwt)
    config = uint(1, 1) + uint(2, max_tokens) + uint(3, 400) + fixed64(5, 1.0) + uint(7, 40) + fixed64(8, .95)
    trajectory_ref = text(1, trajectory) + uint(3, 4) + uint(4, 14)
    return (blob(1, metadata) + (text(2, system) if system else b"") +
        b"".join(msg for c in contents for msg in _pack_content(c)) + uint(7, 5) + blob(8, config) +
        b"".join(_pack_tool(t) for t in tools) + blob(15, trajectory_ref) +
        text(16, cascade) + uint(20, 1) + text(21, model_uid))


def _decode_chat_frame(data: bytes) -> list[tuple[str, Any]]:
    result: list[tuple[str, Any]] = []
    signature = signature_type = None
    for number, wire, value in fields(data):
        if wire == 2 and isinstance(value, bytes):
            if number == 3 and value: result.append(("text", value.decode(errors="replace")))
            elif number == 9 and value: result.append(("thinking", value.decode(errors="replace")))
            elif number == 10: signature = value.decode(errors="replace")
            elif number == 21: signature_type = value.decode(errors="replace")
            elif number == 6:
                call_id = name = args = None
                for inner, wt, val in fields(value):
                    if wt == 2 and isinstance(val, bytes):
                        if inner == 1: call_id = val.decode()
                        elif inner == 2: name = val.decode()
                        elif inner == 3: args = val.decode()
                if call_id is not None and name is not None: result.append(("tool_start", (call_id, name)))
                if args is not None: result.append(("tool_args", (call_id, args)))
            elif number == 28:
                usage: dict[str, int] = {}
                for n, w, metric_message in fields(value):
                    if n != 2 or w != 2 or not isinstance(metric_message, bytes): continue
                    metric, metric_value = None, None
                    for fn, fw, fv in fields(metric_message):
                        if fn == 5 and fw == 2 and isinstance(fv, bytes): metric = fv.decode()
                        elif fn == 4 and fw == 2 and isinstance(fv, bytes):
                            for dn, dw, dv in fields(fv):
                                if dn == 2 and dw == 5 and isinstance(dv, bytes): metric_value = struct.unpack("<f", dv)[0]
                    if metric and metric_value is not None: usage[metric] = round(metric_value)
                if usage: result.append(("usage", usage))
        elif number == 11 and wire == 0 and value: result.append(("redacted", True))
        elif number == 5 and wire == 0:
            result.append(("finish", "tool_calls" if value == 10 else "length" if value in (1, 3) else "stop"))
    if signature: result.append(("signature", (signature, signature_type)))
    return result


async def generate(model_uid: str, system: str, contents: list[Any], tools: list[Any], max_tokens: int = 128_000) -> AsyncIterator[tuple[str, Any]]:
    key, host = credentials()
    timeout = httpx.Timeout(300, connect=30)
    async with httpx.AsyncClient(timeout=timeout) as client:
        jwt = await _user_jwt(client, key, host)
        session = str(uuid.uuid4())
        payload = _request(model_uid, key, jwt, system, contents, tools, session, max_tokens)
        response = await client.post(f"{host}/exa.api_server_pb.ApiServerService/GetChatMessage",
            headers={"Content-Type": "application/connect+proto", "Connect-Protocol-Version": "1",
                     "Connect-Content-Encoding": "gzip", "Connect-Accept-Encoding": "gzip"},
            content=connect_frame(payload))
        if not response.is_success:
            raise RuntimeError(f"Devin GetChatMessage HTTP {response.status_code}: {response.text[:300]}")
        saw_eos = False
        for trailer, frame in connect_payloads(response.content):
            if trailer:
                saw_eos = True
                trailer_data = frame.decode(errors="replace")
                try:
                    error = json.loads(trailer_data).get("error", {}).get("message")
                except (ValueError, AttributeError):
                    error = None
                if error: raise RuntimeError(str(error))
                continue
            for event in _decode_chat_frame(frame):
                yield event
        if not saw_eos: raise RuntimeError("Devin stream ended without an EOS trailer")
