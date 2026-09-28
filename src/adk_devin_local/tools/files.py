"""Root-confined filesystem operations for ADK agents."""
from __future__ import annotations

import os
import shutil
from pathlib import Path


class FileTools:
    """Filesystem tools confined to one resolved project root."""

    def __init__(self, root: str | Path):
        self.root = Path(root).expanduser().resolve(strict=True)
        if not self.root.is_dir():
            raise ValueError("workspace root must be a directory")

    def _path(self, relative_path: str, *, allow_missing: bool = False) -> Path:
        # Absolute paths are honored — souls legitimately work in git
        # worktrees (e.g. /tmp/wt-issue-97) outside the repo root.
        raw = Path(relative_path).expanduser()
        candidate = (raw if raw.is_absolute() else self.root / raw).resolve(strict=False)
        allowed = [self.root, self.root.parent, Path("/tmp")]
        for extra in os.environ.get("ADK_FILE_ROOTS", "").split(os.pathsep):
            if extra.strip():
                allowed.append(Path(extra).expanduser())
        if not any(
            candidate == a or a in candidate.parents for a in allowed
        ):
            raise ValueError(
                "path escapes the allowed roots (workspace, its parent, /tmp)"
            )
        if not allow_missing:
            candidate.stat()  # preserve normal FileNotFoundError after the boundary check
        return candidate

    def read_file(self, path: str) -> str:
        """Read a UTF-8 text file (workspace, sibling dirs, or /tmp)."""
        target = self._path(path)
        if not target.is_file():
            raise ValueError("path is not a regular file")
        return target.read_text(encoding="utf-8")

    def create_file(self, path: str, content: str) -> str:
        """Create a new UTF-8 file; fails if a file already exists."""
        target = self._path(path, allow_missing=True)
        target.parent.mkdir(parents=True, exist_ok=True)
        # Re-resolve after mkdir to defend against symlink races in parents.
        target = self._path(path, allow_missing=True)
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(content)
        return f"Created {path} ({len(content)} characters)."

    def write_file(self, path: str, content: str) -> str:
        """Replace a UTF-8 file's contents inside the workspace."""
        target = self._path(path, allow_missing=True)
        target.parent.mkdir(parents=True, exist_ok=True)
        target = self._path(path, allow_missing=True)
        target.write_text(content, encoding="utf-8")
        return f"Wrote {path} ({len(content)} characters)."

    def edit_file(self, path: str, old_text: str, new_text: str) -> str:
        """Replace exactly one matching text fragment in a file."""
        target = self._path(path)
        original = target.read_text(encoding="utf-8")
        count = original.count(old_text)
        if count != 1:
            raise ValueError(f"expected exactly one match; found {count}")
        target.write_text(original.replace(old_text, new_text, 1), encoding="utf-8")
        return f"Updated {path}."

    def list_files(self, path: str = ".", max_entries: int = 200) -> list[str]:
        """List files and directories under a workspace directory."""
        target = self._path(path)
        if not target.is_dir():
            raise ValueError("path is not a directory")
        items = sorted(target.iterdir(), key=lambda item: (not item.is_dir(), item.name))[:max(1, min(max_entries, 500))]
        return [f"{item.relative_to(self.root)}{'/' if item.is_dir() else ''}" for item in items]

    def search_files(self, query: str, glob: str = "**/*", max_matches: int = 50) -> list[dict[str, str]]:
        """Search text files under the workspace for a literal string."""
        if Path(glob).is_absolute() or ".." in Path(glob).parts:raise ValueError("glob must stay within workspace")
        matches=[]
        ignored={".git", ".venv", "node_modules", "__pycache__", ".codegraph"}
        for target in self.root.glob(glob):
            if len(matches)>=max(1,min(max_matches,200)):break
            relative=target.relative_to(self.root)
            if ignored.intersection(relative.parts):continue
            target=self._path(str(relative),allow_missing=False)
            if not target.is_file():continue
            try:
                with target.open("r",encoding="utf-8") as stream:
                    for number,line in enumerate(stream,1):
                        if query.lower() in line.lower():
                            matches.append({"path":str(target.relative_to(self.root)),"line":str(number),"text":line.rstrip()[:500]})
                            if len(matches)>=max(1,min(max_matches,200)):break
            except (UnicodeDecodeError,OSError):continue
        return matches

    def delete_file(self, path: str, confirm: bool = False) -> str:
        """Delete one regular file; requires confirm=true."""
        if not confirm:
            raise ValueError("deletion requires confirm=true")
        target = self._path(path)
        if not target.is_file():
            raise ValueError("only regular files can be deleted")
        target.unlink()
        return f"Deleted {path}."

    def move_file(self, source: str, destination: str, confirm: bool = False) -> str:
        """Move/rename a file in the workspace; overwriting requires confirmation."""
        src = self._path(source)
        dst = self._path(destination, allow_missing=True)
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst = self._path(destination, allow_missing=True)
        if dst.exists() and not confirm:
            raise ValueError("destination exists; pass confirm=true to overwrite")
        if not src.is_file():
            raise ValueError("source must be a regular file")
        shutil.move(str(src), str(dst))
        return f"Moved {source} to {destination}."
