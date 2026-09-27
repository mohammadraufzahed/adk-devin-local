"""Pi-plugin-compatible ADK tool module."""
from __future__ import annotations

import os
from typing import Any
import httpx

class JevTools:
    async def _jev(self, instructions: str, candidates: dict[str,str], state: str) -> Any:
        key=os.environ.get("OPENROUTER_API_KEY")
        if not key:return {"error":"OPENROUTER_API_KEY not configured; decision service unavailable."}
        async with httpx.AsyncClient(timeout=20) as client:
            response=await client.post("https://openrouter.ai/api/alpha/decisions",
                headers={"Authorization":f"Bearer {key}","X-Title":"adk-devin-local","Content-Type":"application/json"},
                json={"model":os.environ.get("OPENROUTER_MODEL","typesafe/jev-1.13"),"state":{"message":state[:2000]},
                      "questions":{"pick":{"type":"choice","instructions":instructions[:1000],"criteria":candidates}}})
            response.raise_for_status(); body=response.json()
        answer=next(iter((body.get("answers") or {}).values()),{})
        return {"choice":answer.get("choice"),"confidence":answer.get("confidence",0)}

    async def jev_decide(self, question: str, options: list[str], context: str = "") -> Any:
        """Ask the structured Jev decision service to choose exactly one option."""
        if not options:return {"error":"At least one option is required."}
        return await self._jev(question,{option:option for option in options[:30]},context or question)

    async def jev_pick(self, goal: str, items: list[str], context: str = "") -> Any:
        """Pick the best candidate for a goal using the Jev decision service."""
        if not items:return {"error":"At least one candidate is required."}
        criteria={f"item_{i+1}":item[:300] for i,item in enumerate(items[:30])}
        result=await self._jev(f"Choose the candidate best serving: {goal}",criteria,context or "\n".join(items))
        try:
            index=int(str(result.get("choice","")).removeprefix("item_"))-1
            result["picked"]=items[index] if 0<=index<len(items) else None
        except (ValueError,AttributeError):result["picked"]=None
        return result
