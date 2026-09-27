"""Google ADK BaseLlm implementation for Devin Local (experimental)."""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from typing import Any

from google.adk.models import BaseLlm
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import types

from .client import generate


class DevinLocal(BaseLlm):
    """Use a Devin Local model UID while ADK retains tool/session control.

    Pass the exact ``model_uid`` reported by ``devin models list --format json``.
    The wire protocol is private and this class is not affiliated with Cognition.
    """

    @property
    def capabilities(self):
        # Devin endpoint accepts function declarations and JSON schemas.
        from google.adk.models._capabilities import LlmCapabilities

        return LlmCapabilities(output_schema_and_tools=False)

    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        system = llm_request.config.system_instruction
        if isinstance(system, types.Content):
            system = "\n".join(p.text or "" for p in (system.parts or []))
        system = system or ""
        tools = list(llm_request.config.tools or [])
        text_parts: list[str] = []
        thinking_parts: list[str] = []
        calls: dict[str, dict[str, Any]] = {}
        active_call_id: str | None = None
        usage: dict[str, int] = {}

        max_tokens = llm_request.config.max_output_tokens or 128_000
        async for kind, value in generate(
            self.model, system, list(llm_request.contents), tools, max_tokens
        ):
            if kind == "text":
                text_parts.append(value)
                if stream:
                    yield LlmResponse(
                        content=types.Content(
                            role="model", parts=[types.Part(text=value)]
                        ),
                        partial=True,
                    )
            elif kind == "thinking":
                thinking_parts.append(value)
                if stream:
                    yield LlmResponse(
                        content=types.Content(
                            role="model", parts=[types.Part(text=value, thought=True)]
                        ),
                        partial=True,
                    )
            elif kind == "tool_start":
                call_id, name = value
                active_call_id = call_id
                calls[call_id] = {"id": call_id, "name": name, "args_text": ""}
            elif kind == "tool_args":
                call_id, delta = value
                # Devin streams later argument deltas without repeating the
                # function-call id. Match them to the active call, as the
                # protocol's sequential tool-call stream requires.
                target_id = call_id or active_call_id
                if target_id is None or target_id not in calls:
                    raise RuntimeError(
                        "Devin streamed tool arguments without a matching call"
                    )
                calls[target_id]["args_text"] += delta
            elif kind == "usage":
                usage.update(value)

        final_parts: list[types.Part] = []
        if thinking_parts:
            final_parts.append(types.Part(text="".join(thinking_parts), thought=True))
        if text_parts:
            final_parts.append(types.Part(text="".join(text_parts)))
        for item in calls.values():
            try:
                args = json.loads(item["args_text"] or "{}")
            except json.JSONDecodeError as exc:
                raise RuntimeError(
                    f"Devin returned invalid arguments for tool {item['name']}"
                ) from exc
            final_parts.append(
                types.Part(
                    function_call=types.FunctionCall(
                        id=item["id"], name=item["name"], args=args
                    )
                )
            )
        metadata = (
            types.GenerateContentResponseUsageMetadata(
                prompt_token_count=usage.get("input_tokens", 0),
                candidates_token_count=usage.get("output_tokens", 0),
                total_token_count=usage.get("input_tokens", 0)
                + usage.get("output_tokens", 0),
            )
            if usage
            else None
        )
        if not stream:
            yield LlmResponse(
                content=types.Content(role="model", parts=final_parts),
                usage_metadata=metadata,
            )
        else:
            yield LlmResponse(
                content=types.Content(role="model", parts=final_parts),
                partial=False,
                turn_complete=True,
                usage_metadata=metadata,
            )
