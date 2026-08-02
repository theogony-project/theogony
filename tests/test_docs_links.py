"""
Guards the repository's own documentation against link rot.

Every relative markdown link in a tracked ``*.md`` file must resolve to a
path that is itself tracked. Broken cross-references are cheap to introduce
(a doc moves, a ticket is archived) and expensive for an agent that follows
them, so the check runs in the normal ``pytest -q`` matrix rather than as an
optional lint.

Resolution is against git rather than the working tree on purpose. A link
into a gitignored path resolves fine for whoever wrote it and is dead for
everyone who clones the repository — the working tree cannot tell those two
cases apart, and the second is the one that matters.

External links (``http``, ``https``, ``mailto``) and pure anchors are out of
scope: verifying them would need network access. Links inside fenced code
blocks are skipped — they are illustrations, not navigation.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from urllib.parse import unquote

REPO_ROOT = Path(__file__).resolve().parent.parent

MARKDOWN_LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
FENCE = re.compile(r"^\s{0,3}(```|~~~)")
EXTERNAL_PREFIXES = ("http://", "https://", "mailto:", "#")


def _git_ls_files(*patterns: str) -> list[str]:
    result = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "ls-files", *patterns],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.split()


def _tracked_paths() -> set[Path]:
    """Tracked files plus every directory on the way to them."""
    paths: set[Path] = set()
    for entry in _git_ls_files():
        current = REPO_ROOT / entry
        paths.add(current)
        for parent in current.parents:
            if parent == REPO_ROOT:
                break
            paths.add(parent)
    return paths


def _broken_links_in(relative_path: str, tracked: set[Path]) -> list[str]:
    path = REPO_ROOT / relative_path
    broken: list[str] = []
    in_fence = False

    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue

        for target in MARKDOWN_LINK.findall(line):
            if target.startswith(EXTERNAL_PREFIXES):
                continue
            file_part = unquote(target.split("#", 1)[0])
            if not file_part:
                continue
            if (path.parent / file_part).resolve() not in tracked:
                broken.append(f"{relative_path}:{lineno} -> {target}")

    return broken


def test_no_broken_relative_markdown_links() -> None:
    markdown_files = _git_ls_files("*.md")
    assert markdown_files, "expected git to report tracked markdown files"

    tracked = _tracked_paths()
    broken = [entry for path in markdown_files for entry in _broken_links_in(path, tracked)]

    assert not broken, "broken relative markdown links:\n" + "\n".join(broken)
