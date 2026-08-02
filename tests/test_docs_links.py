"""
Guards the repository's own documentation against link rot.

Every relative markdown link in a tracked ``*.md`` file must resolve to an
existing path. Broken cross-references are cheap to introduce (a doc moves,
a ticket is archived) and expensive for an agent that follows them, so the
check runs in the normal ``pytest -q`` matrix rather than as an optional
lint.

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


def _tracked_markdown_files() -> list[str]:
    result = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "ls-files", "*.md"],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.split()


def _broken_links_in(relative_path: str) -> list[str]:
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
            if not (path.parent / file_part).resolve().exists():
                broken.append(f"{relative_path}:{lineno} -> {target}")

    return broken


def test_no_broken_relative_markdown_links() -> None:
    tracked = _tracked_markdown_files()
    assert tracked, "expected git to report tracked markdown files"

    broken = [entry for path in tracked for entry in _broken_links_in(path)]

    assert not broken, "broken relative markdown links:\n" + "\n".join(broken)
