"""Persistent local equivalents for memory, wiki, project, cron, watch and team tools."""
from __future__ import annotations

import json
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any

import httpx


class StatefulTools:
    def __init__(self, root: str | Path, state_dir: str | Path | None = None):
        self.root = Path(root).expanduser().resolve(strict=True)
        self.state = Path(state_dir or os.environ.get("ADK_DEVIN_STATE_DIR", self.root / ".adk-devin")).expanduser().resolve()
        self.state.mkdir(parents=True, exist_ok=True)

    def _load(self, name: str, default: Any) -> Any:
        path = self.state / name
        try: return json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError: return default
        except (OSError, ValueError): return default

    def _save(self, name: str, value: Any) -> None:
        path = self.state / name
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temp, path)

    def memory_store(self, note: str, key: str = "default") -> str:
        """Persist a note in this workspace's local agent memory."""
        if not note.strip(): return "Memory note must not be empty."
        data = self._load("memory.json", [])
        row = {"id": uuid.uuid4().hex[:12], "key": key[:100], "note": note[:8000], "at": time.time()}
        data.append(row); self._save("memory.json", data)
        return f"Stored memory {row['id']}."

    def memory_recall(self, query: str = "", limit: int = 10, key: str = "") -> list[dict[str, Any]]:
        """Search notes persisted by memory_store."""
        rows = self._load("memory.json", [])
        terms = query.lower().split()
        scored = []
        for row in rows:
            if key and row.get("key") != key: continue
            text = (row.get("key", "") + " " + row.get("note", "")).lower()
            score = sum(text.count(term) for term in terms)
            if not terms or score: scored.append((score, row))
        scored.sort(key=lambda item: (-item[0], -item[1].get("at", 0)))
        return [row for _, row in scored[:max(1, min(limit, 50))]]

    def memory_forget(self, match: str) -> str:
        """Delete memories containing the supplied substring."""
        rows = self._load("memory.json", [])
        needle=match.lower()
        filtered = [row for row in rows if needle not in (row.get("note", "")).lower()]
        removed=len(rows)-len(filtered)
        if not removed:return "No matching memories found."
        self._save("memory.json", filtered)
        return f"Forgot {removed} matching memory/memories."

    def wiki_write(self, title: str, content: str) -> str:
        """Create or replace a Markdown page in the workspace wiki."""
        slug = re.sub(r"[^a-z0-9-]+", "-", title.lower()).strip("-")[:80]
        if not slug: return "Invalid page title."
        directory = self.state / "wiki"; directory.mkdir(exist_ok=True)
        (directory / f"{slug}.md").write_text(f"# {title[:160]}\n\n{content[:40_000]}\n", encoding="utf-8")
        return f"Saved wiki page '{title}'."

    def wiki_read(self, title: str) -> str:
        """Read a Markdown wiki page by title/slug."""
        slug = re.sub(r"[^a-z0-9-]+", "-", title.lower()).strip("-")[:80]
        path = self.state / "wiki" / f"{slug}.md"
        try: return path.read_text(encoding="utf-8")
        except FileNotFoundError: return "Wiki page not found."

    def wiki_search(self, query: str) -> list[dict[str, str]]:
        """Search titles and bodies of local Markdown wiki pages."""
        pages = self.state / "wiki"; terms = query.lower().split(); found = []
        if not pages.exists(): return found
        for path in pages.glob("*.md"):
            text = path.read_text(encoding="utf-8")
            if all(term in (path.stem + " " + text).lower() for term in terms):
                found.append({"page": path.stem, "excerpt": text[:1000]})
        return found[:30]

    def blackboard_write(self, key: str, value: str) -> str:
        """Set a shared key/value note on this workspace's agent blackboard."""
        data = self._load("blackboard.json", {})
        data[key[:160]] = {"value": value[:12_000], "updated_at": time.time()}
        self._save("blackboard.json", data)
        return f"Updated blackboard key '{key[:160]}'."

    def blackboard_read(self, key: str = "") -> Any:
        """Read one blackboard entry, or list all current entries."""
        data = self._load("blackboard.json", {})
        return data.get(key) if key else data

    def project_list(self) -> list[dict[str, Any]]:
        """List locally registered project roots."""
        return self._load("projects.json", [])

    def project_register(self, name: str, path: str, description: str = "") -> str:
        """Register an existing project directory for reference (does not change cwd)."""
        root = Path(path).expanduser().resolve(strict=True)
        if not root.is_dir(): return "Project path is not a directory."
        rows = self._load("projects.json", [])
        if any(item.get("name") == name for item in rows): return "Project name already registered."
        rows.append({"name": name[:100], "path": str(root), "description": description[:1000]})
        self._save("projects.json", rows)
        return f"Registered project '{name}'."

    def project_forget(self, name: str) -> str:
        """Remove a project from this local registry; does not delete files."""
        rows = self._load("projects.json", [])
        filtered = [item for item in rows if item.get("name") != name]
        if len(filtered) == len(rows): return "Project not found."
        self._save("projects.json", filtered)
        return f"Forgot project '{name}'."

    def cron_add(self, spec: str, prompt: str, soul: str = "", silent: bool = True, times: int = 0, project: str = "") -> str:
        """Record a scheduled task definition. Requires a separately running scheduler to execute."""
        if not re.fullmatch(r"(?:every:\d+[smh]?|in:\d+[smh]?|daily:\d{2}:\d{2}|once:\d{9,}|cron:.+)", spec):
            return "Invalid schedule syntax. Use every:90, in:30, daily:09:30, once:<unix-ts>, or cron:<5-field expression>."
        jobs = self._load("cron.json", [])
        row = {"id": uuid.uuid4().hex[:12], "spec": spec, "prompt": prompt[:8000], "soul": soul[:100], "silent": silent, "project": project[:200], "times": max(0, times), "paused": False, "created": time.time()}
        jobs.append(row); self._save("cron.json", jobs)
        return f"Recorded schedule {row['id']}. Note: this ADK package does not run a scheduler daemon; configure a host scheduler to execute jobs."

    def cron_list(self, all: bool = True) -> list[dict[str, Any]]:
        """List recorded scheduled task definitions (paused included when all=true)."""
        jobs=self._load("cron.json", [])
        return jobs if all else [job for job in jobs if not job.get("paused")]

    def cron_edit(self, job_id: str, spec: str = "", prompt: str = "") -> str:
        """Edit a recorded cron job's schedule or prompt."""
        jobs=self._load("cron.json", [])
        for job in jobs:
            if job.get("id")==job_id:
                if spec:
                    if not re.fullmatch(r"(?:every:\d+[smh]?|in:\d+[smh]?|daily:\d{2}:\d{2}|once:\d{9,}|cron:.+)",spec):return "Invalid schedule syntax."
                    job["spec"]=spec
                if prompt:job["prompt"]=prompt[:8000]
                self._save("cron.json",jobs)
                return "Schedule updated (host scheduler notifies external to this package)."
        return "Schedule not found."

    def cron_pause(self, job_id: str, paused: bool = True) -> str:
        """Pause or resume a recorded scheduled task."""
        jobs = self._load("cron.json", [])
        for job in jobs:
            if job.get("id") == job_id:
                job["paused"] = paused; self._save("cron.json", jobs)
                return "Schedule paused." if paused else "Schedule resumed."
        return "Schedule not found."

    def cron_remove(self, job_id: str) -> str:
        """Remove a scheduled task definition."""
        jobs = self._load("cron.json", []); kept = [job for job in jobs if job.get("id") != job_id]
        if len(jobs) == len(kept): return "Schedule not found."
        self._save("cron.json", kept); return "Schedule removed."

    def webwatch_add(self, url: str, name: str = "") -> str:
        """Add an RSS/Atom feed URL to the local watch list."""
        try:
            from .web import _public_url
            url=_public_url(url)
        except ValueError as exc:return str(exc)
        feeds = self._load("feeds.json", [])
        if any(feed["url"] == url for feed in feeds): return "Feed already watched."
        feeds.append({"url": url, "name": name[:120] or url}); self._save("feeds.json", feeds)
        return "Feed added. Use webwatch_check to fetch latest entries."

    def webwatch_list(self) -> list[dict[str, str]]:
        """List watched feeds."""
        return self._load("feeds.json", [])

    def webwatch_remove(self, url: str) -> str:
        """Stop watching a feed URL."""
        feeds=self._load("feeds.json", [])
        remaining=[feed for feed in feeds if feed.get("url") != url]
        if len(remaining)==len(feeds): return "Feed not found."
        self._save("feeds.json",remaining)
        return "Feed removed."

    async def webwatch_check(self) -> list[dict[str, str]]:
        """Fetch watched RSS/Atom feeds and return recent entry titles/links."""
        results = []
        feeds=self._load("feeds.json", [])
        async with httpx.AsyncClient(timeout=15, follow_redirects=False, headers={"User-Agent": "adk-devin-local/0.1"}) as client:
            for feed in feeds[:30]:
                try:
                    from .web import _public_url
                    response = await client.get(_public_url(feed["url"])); response.raise_for_status()
                    import xml.etree.ElementTree as ET
                    root = ET.fromstring(response.content)
                    items=[]
                    for item in list(root.iter())[-40:]:
                        if item.tag.endswith(("item", "entry")):
                            values = {node.tag.split("}")[-1]: (node.attrib.get("href") or node.text or "").strip() for node in item}
                            title = values.get("title", "")
                            link = values.get("link", "") or values.get("guid", "")
                            if title: items.append({"feed": feed["name"], "title": title[:300], "link": link[:1000]})
                    previous=feed.get("last_seen", "")
                    if previous:
                        fresh=[]
                        for item in items:
                            if item["link"]==previous:break
                            if item["link"]:fresh.append(item)
                    else:fresh=items
                    results.extend(fresh[:8])
                    if items:
                        feed["last_seen"]=items[0]["link"]
                    feed["checked_at"]=time.time()
                except Exception as exc:
                    results.append({"feed": feed.get("name", feed["url"]), "error": str(exc)[:300]})
        self._save("feeds.json",feeds)
        return results

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

    def project_use(self, name: str) -> dict[str, str]:
        """Resolve a registered project name to its local path."""
        for item in self._load("projects.json", []):
            if item.get("name")==name:return {"name":name,"path":item["path"]}
        return {"error":"Project not found."}

    def bb_claim(self, key: str, owner: str, ttl_s: int = 900, note: str = "") -> dict[str, Any]:
        """Pi-compatible alias for an expiring blackboard claim."""
        return self.blackboard_claim(key,owner,ttl_s,note)

    def team_roster(self) -> list[str]:
        """List available soul/agent identities from SOULS_DIR."""
        directory = os.environ.get("SOULS_DIR")
        if not directory: return ["No SOULS_DIR configured."]
        return sorted(path.stem for path in Path(directory).glob("*.md"))

    def team_say(self, message: str, to: str = "all") -> str:
        """Send a non-blocking request to the configured Pi team mailbox."""
        directory = os.environ.get("PI_TEAM_DIR")
        if not directory: return "PI_TEAM_DIR is not configured; no team mailbox is available."
        target = Path(directory) / "requests"; target.mkdir(parents=True, exist_ok=True)
        rid = uuid.uuid4().hex
        request = {"id": rid, "from": os.environ.get("PI_TEAM_FROM", "adk"), "to": to,
                   "kind": "say", "text": message[:8000], "at": time.time()}
        (target / f"{rid}.json").write_text(json.dumps(request), encoding="utf-8")
        return f"Team message queued ({rid})."

    async def team_ask(self, to: str, question: str, timeout_seconds: int = 120) -> str:
        """Ask a teammate via PI_TEAM_DIR mailbox and wait for its host watcher to reply."""
        directory = os.environ.get("PI_TEAM_DIR")
        if not directory: return "PI_TEAM_DIR is not configured; no team mailbox is available."
        target = Path(directory); reqdir = target / "requests"; repdir = target / "replies"
        reqdir.mkdir(parents=True, exist_ok=True); repdir.mkdir(parents=True, exist_ok=True)
        rid = uuid.uuid4().hex
        req = {"id": rid, "from": os.environ.get("PI_TEAM_FROM", "adk"), "to": to,
               "kind": "ask", "text": question[:8000], "at": time.time()}
        (reqdir / f"{rid}.json").write_text(json.dumps(req), encoding="utf-8")
        deadline = time.monotonic() + max(1, min(timeout_seconds, 600))
        while time.monotonic() < deadline:
            reply = repdir / f"{rid}.json"
            if reply.exists():
                try: return json.loads(reply.read_text()).get("text", "(empty reply)")
                except (ValueError, OSError): return "Received an unreadable team reply."
            import asyncio
            await asyncio.sleep(1)
        return f"Timed out waiting for teammate; request {rid} remains queued."

    def team_task(self, to: str, task: str, budget_min: int = 10) -> str:
        """Delegate work asynchronously through the Pi team host mailbox."""
        directory=os.environ.get("PI_TEAM_DIR")
        if not directory:return "PI_TEAM_DIR is not configured; no team mailbox is available."
        reqdir=Path(directory)/"requests"; reqdir.mkdir(parents=True,exist_ok=True)
        rid=uuid.uuid4().hex
        request={"id":rid,"from":os.environ.get("PI_TEAM_FROM","adk"),"to":to,"kind":"task","text":task[:8000],"budget_s":max(60,min(budget_min,120))*60,"at":time.time()}
        (reqdir/f"{rid}.json").write_text(json.dumps(request),encoding="utf-8")
        return f"Task delegated to {to} ({rid}); host watcher must be running."

    def team_emit(self, event: str, payload: str = "", to: str = "auto") -> str:
        """Emit a typed event to subscribed agents through the team mailbox."""
        directory=os.environ.get("PI_TEAM_DIR")
        if not directory:return "PI_TEAM_DIR is not configured; no team mailbox is available."
        reqdir=Path(directory)/"requests"; reqdir.mkdir(parents=True,exist_ok=True)
        rid=uuid.uuid4().hex
        request={"id":rid,"from":os.environ.get("PI_TEAM_FROM","adk"),"to":to,"kind":"event","text":event[:120]+(" "+payload[:7000] if payload else ""),"at":time.time()}
        (reqdir/f"{rid}.json").write_text(json.dumps(request),encoding="utf-8")
        return f"Event {event} emitted ({rid})."

    async def team_status(self) -> str:
        """Ask the host watcher for team queue and activity status."""
        return await self._mailbox_request("status", "", 15)

    async def project_current(self) -> str:
        """Resolve current project context through the host mailbox when available."""
        return await self._mailbox_request("project", "current|||", 20)

    async def _mailbox_request(self, kind: str, text: str, timeout: int) -> str:
        directory=os.environ.get("PI_TEAM_DIR")
        if not directory:return f"PI_TEAM_DIR is not configured; cannot query host {kind}."
        target=Path(directory); reqdir=target/"requests"; repdir=target/"replies"
        reqdir.mkdir(parents=True,exist_ok=True); repdir.mkdir(parents=True,exist_ok=True)
        rid=uuid.uuid4().hex
        request={"id":rid,"from":os.environ.get("PI_TEAM_FROM","adk"),"to":"host","kind":kind,"text":text,"at":time.time()}
        (reqdir/f"{rid}.json").write_text(json.dumps(request),encoding="utf-8")
        import asyncio
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            reply=repdir/f"{rid}.json"
            if reply.exists():
                try:return str(json.loads(reply.read_text()).get("text",""))
                except (ValueError,OSError):pass
            await asyncio.sleep(.5)
        return f"Host {kind} request timed out ({rid})."

    def team_handoff(self, to: str, task: str) -> str:
        """Hand a request to a team member; host mailbox watcher must be running."""
        directory = os.environ.get("PI_TEAM_DIR")
        if not directory: return "PI_TEAM_DIR is not configured; no team mailbox is available."
        reqdir = Path(directory) / "requests"; reqdir.mkdir(parents=True, exist_ok=True)
        rid = uuid.uuid4().hex
        request = {"id": rid, "from": os.environ.get("PI_TEAM_FROM", "adk"), "to": to,
                   "kind": "handoff", "text": task[:8000], "at": time.time()}
        (reqdir / f"{rid}.json").write_text(json.dumps(request), encoding="utf-8")
        return f"Request handed to {to} ({rid}); the host mailbox watcher must be running."
