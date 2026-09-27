"""Pi-plugin-compatible ADK tool module."""
from __future__ import annotations

import json, os, re, time
from typing import Any
from .stateful import StatefulTools

class BlackboardTools(StatefulTools):
    def blackboard_set(self, key: str, value: str) -> str:
        """Write a shared board value available to other local ADK runs."""
        safe=re.sub(r"[^\w.:#-]", "_", key)[:120]
        if not safe:return "Invalid board key."
        path=self.state/"blackboard"; path.mkdir(exist_ok=True)
        tmp=path/(safe+".tmp"); target=path/safe
        tmp.write_text(value[:100_000],encoding="utf-8"); os.replace(tmp,target)
        return f"Set blackboard key '{safe}'."

    def bb_set(self, key: str, value: str) -> str:
        """Pi-compatible alias for blackboard_set."""
        return self.blackboard_set(key,value)

    def blackboard_get(self, key: str) -> str:
        """Read a shared board value."""
        safe=re.sub(r"[^\w.:#-]", "_", key)[:120]
        path=self.state/"blackboard"/safe
        try:return path.read_text(encoding="utf-8")
        except FileNotFoundError:return "(empty)"

    def bb_get(self, key: str) -> str:
        """Pi-compatible alias for blackboard_get."""
        return self.blackboard_get(key)

    def blackboard_append(self, key: str, line: str) -> str:
        """Append a line to a shared blackboard ledger."""
        safe=re.sub(r"[^\w.:#-]", "_", key)[:120]
        path=self.state/"blackboard"; path.mkdir(exist_ok=True)
        with (path/safe).open("a",encoding="utf-8") as stream:stream.write(line[:4000]+"\n")
        return "Appended to blackboard."

    def bb_append(self, key: str, line: str) -> str:
        """Pi-compatible alias for blackboard_append."""
        return self.blackboard_append(key,line)

    def blackboard_list(self, prefix: str = "") -> list[dict[str, Any]]:
        """List blackboard keys, newest first, optionally by prefix."""
        path=self.state/"blackboard"
        if not path.exists():return []
        found=[]
        for item in path.iterdir():
            if item.is_file() and not item.name.endswith(".tmp") and item.name.startswith(prefix):
                stat=item.stat(); found.append({"key":item.name,"updated_at":stat.st_mtime,"size":stat.st_size})
        return sorted(found,key=lambda row:row["updated_at"],reverse=True)[:200]

    def bb_list(self, prefix: str = "") -> list[dict[str, Any]]:
        """Pi-compatible alias for blackboard_list."""
        return self.blackboard_list(prefix)

    def blackboard_claim(self, key: str, owner: str, ttl_seconds: int = 900, note: str = "") -> dict[str, Any]:
        """Acquire or inspect an expiring blackboard work claim."""
        safe=re.sub(r"[^\w.:#-]", "_", key)[:120]
        path=self.state/"blackboard"; path.mkdir(exist_ok=True); target=path/("claim_"+safe)
        now=time.time()
        try:current=json.loads(target.read_text(encoding="utf-8"))
        except (OSError,ValueError):current=None
        if current and current.get("expires",0)>now and current.get("owner")!=owner:
            return {"claimed":False,"owner":current.get("owner"),"note":current.get("note","")}
        claim={"owner":owner[:100],"note":note[:1000],"created":now,"expires":now+max(1,min(ttl_seconds,86400))}
        tmp=target.with_suffix(".tmp"); tmp.write_text(json.dumps(claim),encoding="utf-8"); os.replace(tmp,target)
        return {"claimed":True,**claim}

    def bb_claim(self, key: str, owner: str, ttl_s: int = 900, note: str = "") -> dict[str, Any]:
        """Pi-compatible alias for an expiring blackboard claim."""
        return self.blackboard_claim(key,owner,ttl_s,note)
