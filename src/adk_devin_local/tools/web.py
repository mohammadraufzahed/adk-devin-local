"""DuckDuckGo web search and guarded page extraction."""
from __future__ import annotations

import html
import ipaddress
import socket
from html.parser import HTMLParser
from urllib.parse import parse_qs, quote_plus, urlparse

import httpx


def _public_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Only HTTP(S) URLs are supported.")
    host = parsed.hostname.lower()
    if host in {"localhost", "metadata.google.internal"} or host.endswith((".local", ".internal")):
        raise ValueError("Private/local hosts are not fetchable.")
    try:
        addresses = [ipaddress.ip_address(host)] if host.replace(".", "").isdigit() else [ipaddress.ip_address(info[4][0]) for info in socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80))]
        if any(not address.is_global for address in addresses): raise ValueError("Private/local hosts are not fetchable.")
    except socket.gaierror as exc:
        raise ValueError("Host could not be resolved.") from exc
    return url


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True); self.parts: list[str] = []; self.skip = 0
    def handle_starttag(self, tag: str, attrs):
        if tag in {"script", "style", "noscript", "svg", "nav", "footer"}: self.skip += 1
        if tag in {"p", "br", "div", "li", "h1", "h2", "h3", "tr"}: self.parts.append("\n")
    def handle_endtag(self, tag: str):
        if tag in {"script", "style", "noscript", "svg", "nav", "footer"} and self.skip: self.skip -= 1
        if tag in {"p", "div", "li", "h1", "h2", "h3", "tr"}: self.parts.append("\n")
    def handle_data(self, data: str):
        if not self.skip: self.parts.append(data)


async def web_search(query: str, limit: int = 6) -> list[dict[str, str]]:
    """Search public web pages with DuckDuckGo (no API key required)."""
    async with httpx.AsyncClient(timeout=20, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0 adk-devin-local"}) as client:
        response = await client.get("https://html.duckduckgo.com/html/", params={"q": query[:500]})
        response.raise_for_status()
    class SearchParser(HTMLParser):
        def __init__(self): super().__init__(); self.items=[]; self.current=None; self.capture=None
        def handle_starttag(self, tag, attrs):
            attrs=dict(attrs)
            if tag == "a" and "result__a" in attrs.get("class", ""):
                self.current={"title":"", "url":attrs.get("href", "")}; self.capture="title"
            elif tag == "a" and self.current and "result__snippet" in attrs.get("class", ""): self.capture="snippet"
        def handle_endtag(self, tag):
            if tag == "a" and self.current and self.capture == "title": self.capture=None
            if tag == "a" and self.current and self.capture == "snippet":
                self.items.append(self.current); self.current=None; self.capture=None
        def handle_data(self, data):
            if self.current and self.capture: self.current[self.capture] += data
    parser=SearchParser(); parser.feed(response.text)
    results=[]
    for item in parser.items:
        target=parse_qs(urlparse(item["url"]).query).get("uddg", [item["url"]])[0]
        results.append({"title":html.unescape(item["title"]).strip(), "url":target, "snippet":html.unescape(item.get("snippet", "")).strip()})
    return results[:max(1,min(limit,10))]


async def web_fetch(url: str, max_chars: int = 8000) -> dict[str, str]:
    """Fetch a public HTTP(S) URL and extract readable page text; blocks private-network targets."""
    safe = _public_url(url)
    async with httpx.AsyncClient(timeout=25, follow_redirects=False, headers={"User-Agent": "Mozilla/5.0 adk-devin-local"}) as client:
        response = await client.get(safe)
        if response.is_redirect:
            location=response.headers.get("location", "")
            from urllib.parse import urljoin
            target=_public_url(urljoin(safe, location))
            response=await client.get(target)
        response.raise_for_status()
    parser=_TextExtractor(); parser.feed(response.text)
    text=" ".join(" ".join(parser.parts).split())
    return {"url": str(response.url), "text": text[:max(100,min(max_chars,30_000))]}
