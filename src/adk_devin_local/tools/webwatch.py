"""Pi-plugin-compatible ADK tool module."""
from __future__ import annotations

import httpx, time
import feedparser
from .stateful import StatefulTools
from .websearch import _public_url

class WebwatchTools(StatefulTools):
    def webwatch_add(self, url: str, name: str = "") -> str:
        """Add an RSS/Atom feed URL to the local watch list."""
        try:
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
                    response = await client.get(_public_url(feed["url"])); response.raise_for_status()
                    parsed = feedparser.parse(response.content)
                    items=[]
                    for entry in parsed.entries[:40]:
                        title = str(entry.get("title", "")).strip()
                        link = str(entry.get("link") or entry.get("id") or "").strip()
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
