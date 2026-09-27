"""Pi-plugin-compatible ADK tool module."""
from __future__ import annotations

import re
from .stateful import StatefulTools

class WikiTools(StatefulTools):
    """Shared team wiki — lives at <state_dir>/wiki (sibling of the team
    mailbox when PI_TEAM_DIR is set), so all souls see the same pages."""

    @property
    def _wikidir(self) -> "Path":
        from pathlib import Path
        team = self._e("PI_TEAM_DIR")
        if team:
            return Path(team).parent / "wiki"
        return self.state / "wiki"

    def wiki_write(self, title: str, content: str) -> str:
        """Create or replace a Markdown page in the workspace wiki."""
        slug = re.sub(r"[^a-z0-9-]+", "-", title.lower()).strip("-")[:80]
        if not slug: return "Invalid page title."
        directory = self._wikidir; directory.mkdir(parents=True, exist_ok=True)
        (directory / f"{slug}.md").write_text(f"# {title[:160]}\n\n{content[:40_000]}\n", encoding="utf-8")
        return f"Saved wiki page '{title}'."

    def wiki_read(self, title: str) -> str:
        """Read a Markdown wiki page by title/slug."""
        slug = re.sub(r"[^a-z0-9-]+", "-", title.lower()).strip("-")[:80]
        path = self._wikidir / f"{slug}.md"
        try: return path.read_text(encoding="utf-8")
        except FileNotFoundError: return "Wiki page not found."

    def wiki_list(self) -> list[str]:
        """List all wiki page names."""
        pages = self._wikidir
        if not pages.exists(): return []
        return sorted(p.stem for p in pages.glob("*.md"))

    def wiki_search(self, query: str) -> list[dict[str, str]]:
        """Search titles and bodies of local Markdown wiki pages."""
        pages = self._wikidir; terms = query.lower().split(); found = []
        if not pages.exists(): return found
        for path in pages.glob("*.md"):
            text = path.read_text(encoding="utf-8")
            if all(term in (path.stem + " " + text).lower() for term in terms):
                found.append({"page": path.stem, "excerpt": text[:1000]})
        return found[:30]
