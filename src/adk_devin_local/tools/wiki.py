"""Pi-plugin-compatible ADK tool module."""
from __future__ import annotations

import re
from .stateful import StatefulTools

class WikiTools(StatefulTools):
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
