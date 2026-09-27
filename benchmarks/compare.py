"""Manual paid/live comparison of this adapter and Pi's Devin provider.

The script stores no transcripts or reasoning traces; it prints answer text,
model UID, wall latency, usage and deterministic task scores only.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from google.adk.models.llm_request import LlmRequest
from google.genai import types

from adk_devin_local import DevinLocal

SYSTEM = "You are an evaluation model. Follow the user's requested output format exactly. Do not use tools or add unrelated explanation."
TASKS = [
    ("arithmetic", "Compute 19 * 23. Reply with only the integer.", "437"),
    ("json", 'For [8, 3, 11, 3], return only JSON with keys "count", "sum", "min", "max".', {"count": 4, "sum": 25, "min": 3, "max": 11}),
    ("coding", "Write a Python function unique_in_order(values) that returns a list with duplicates removed while preserving first occurrence order. Return only Python code defining the function.", None),
]
MODELS = [("SWE-1.6", "swe-1-6", "swe-1-6", "high"), ("SWE-2", "swe-2-high", "swe-2", "high")]


def score(task: str, answer: str, expected: Any) -> bool:
    text = answer.strip()
    if task == "arithmetic":
        return text.strip("` \n") == expected
    if task == "json":
        match = re.search(r"\{.*?\}", text, re.S)
        try:
            return match is not None and json.loads(match.group()) == expected
        except json.JSONDecodeError:
            return False
    code = re.sub(r"^```(?:python)?\s*|\s*```$", "", text, flags=re.I).strip()
    try:
        namespace: dict[str, Any] = {}
        exec(compile(code, "<model-answer>", "exec"), {"__builtins__": __builtins__}, namespace)
        return namespace["unique_in_order"]([1, 2, 1, 3, 2]) == [1, 2, 3] and namespace["unique_in_order"]([]) == [] and namespace["unique_in_order"]("banana") == ["b", "a", "n"]
    except Exception:
        return False


async def run_adk(uid: str, prompt: str) -> dict[str, Any]:
    request = LlmRequest(model=uid, contents=[types.Content(role="user", parts=[types.Part(text=prompt)])],
        config=types.GenerateContentConfig(system_instruction=SYSTEM, max_output_tokens=512))
    started = time.perf_counter()
    responses = [response async for response in DevinLocal(model=uid).generate_content_async(request)]
    elapsed = time.perf_counter() - started
    response = responses[-1]
    content = response.content
    answer = "\n".join(part.text for part in (content.parts or []) if part.text and not part.thought) if content else ""
    usage = response.usage_metadata
    return {"elapsed": elapsed, "answer": answer, "input_tokens": getattr(usage, "prompt_token_count", None),
            "output_tokens": getattr(usage, "candidates_token_count", None)}


def run_pi(model_arg: str, thinking: str, prompt: str) -> dict[str, Any]:
    command = ["pi", "--provider", "devin", "--model", f"devin/{model_arg}", "--thinking", thinking,
               "--system-prompt", SYSTEM, "--no-tools", "--no-context-files", "--no-session", "--mode", "json", "--print", prompt]
    started = time.perf_counter()
    result = subprocess.run(command, capture_output=True, text=True, timeout=240, cwd="/tmp")
    elapsed = time.perf_counter() - started
    if result.returncode:
        raise RuntimeError(f"Pi failed ({result.returncode}): {result.stderr[-600:]}")
    message = None
    for line in result.stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "turn_end":
            message = event.get("message")
    if not message:
        raise RuntimeError("Pi output lacked final turn_end")
    answer = "\n".join(item.get("text", "") for item in message.get("content", []) if item.get("type") == "text")
    usage = message.get("usage") or {}
    return {"elapsed": elapsed, "answer": answer, "input_tokens": usage.get("input"),
            "output_tokens": usage.get("output"), "actual_model": message.get("model")}


async def main() -> None:
    results = []
    for model_name, adk_uid, pi_model, pi_thinking in MODELS:
        for task_name, prompt, expected in TASKS:
            for surface in ("ADK", "Pi"):
                try:
                    result = await run_adk(adk_uid, prompt) if surface == "ADK" else await asyncio.to_thread(run_pi, pi_model, pi_thinking, prompt)
                    row = {"model": model_name, "task": task_name, "surface": surface,
                           "score": score(task_name, result["answer"], expected), **result}
                except Exception as exc:
                    row = {"model": model_name, "task": task_name, "surface": surface, "error": str(exc)}
                results.append(row)
                print(json.dumps(row, ensure_ascii=False), flush=True)
    for model_name, *_ in MODELS:
        for surface in ("ADK", "Pi"):
            subset = [r for r in results if r.get("model") == model_name and r.get("surface") == surface and "error" not in r]
            if subset:
                print(json.dumps({"summary": model_name, "surface": surface,
                    "score": f"{sum(bool(r['score']) for r in subset)}/{len(subset)}",
                    "mean_seconds": round(sum(r["elapsed"] for r in subset) / len(subset), 2),
                    "mean_input_tokens": round(sum(r.get("input_tokens") or 0 for r in subset) / len(subset)),
                    "mean_output_tokens": round(sum(r.get("output_tokens") or 0 for r in subset) / len(subset))}, ensure_ascii=False), flush=True)

if __name__ == "__main__":
    asyncio.run(main())
