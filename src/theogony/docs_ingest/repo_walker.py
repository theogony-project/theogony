"""
Walk a repository and return the set of Markdown files in scope for
the docs-aware ingest path.

Scope policy (Pantheon-of-Pantheon seed, v1):

In scope:
- Root: README.md, AGENTS.md, PHILOSOPHY.md, CONTRIBUTING.md
- ``docs/*.md`` — all top-level docs (vision, architecture, glossary,
  the agent-doctrine documents, RELEASING.md, etc.)
- ``prompts/*.md`` — builder + Pantheon-agent prompt files

Explicitly out of scope (genre mismatch or transient):
- ``docs/etappes/*.md`` — historical milestone briefs (the Pantheon
  doc-pass already declared these untouchable)
- ``docs/run_reports/`` — operational data, not vision
- ``docs/cypher_audit/`` — performance audit
- ``genesis_conversation_log.md``, ``cursor_theogony_project_introduction.md``
  — local, gitignored
- ``CODE_OF_CONDUCT.md`` — boilerplate, not project-specific vision
- Any ``.md`` under hidden directories (``.github``, ``.cursor``)

This list is encoded as :data:`DEFAULT_INCLUDE` and :data:`DEFAULT_EXCLUDE`;
either can be overridden when calling :func:`walk_repo` for federation
scenarios where a different operator wants a different scope.
"""

from __future__ import annotations

import fnmatch
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

#: Glob patterns (relative to the repo root) that are eligible for ingest.
DEFAULT_INCLUDE: tuple[str, ...] = (
    "README.md",
    "AGENTS.md",
    "PHILOSOPHY.md",
    "CONTRIBUTING.md",
    "docs/*.md",
    "prompts/*.md",
)

#: Glob patterns to subtract from the include set even when matched.
DEFAULT_EXCLUDE: tuple[str, ...] = (
    "docs/etappes/**",
    "docs/run_reports/**",
    "docs/cypher_audit/**",
    "docs/HISTORICAL_MD_INTENTIONALLY_UNTOUCHED.md",
    "CODE_OF_CONDUCT.md",
    "genesis_conversation_log.md",
    "cursor_theogony_project_introduction.md",
    ".github/**",
    ".cursor/**",
    "venv/**",
    ".venv/**",
)


@dataclass(frozen=True)
class WalkedFile:
    """One Markdown file discovered by :func:`walk_repo`."""

    #: Path relative to the repo root, e.g. ``docs/PANTHEON_VISION.md``.
    rel_path: str
    #: Absolute path on disk for reading.
    abs_path: Path


def walk_repo(
    repo_root: Path,
    *,
    include: Iterable[str] = DEFAULT_INCLUDE,
    exclude: Iterable[str] = DEFAULT_EXCLUDE,
) -> list[WalkedFile]:
    """Return all Markdown files in ``repo_root`` matched by the include
    set and not matched by the exclude set.

    The result is sorted by ``rel_path`` for determinism — two runs
    against the same repo snapshot must produce the same file order
    so the resulting Chronicle dump is byte-stable in git.
    """
    repo_root = repo_root.resolve()
    if not repo_root.is_dir():
        raise NotADirectoryError(f"repo_root is not a directory: {repo_root}")

    include_tuple = tuple(include)
    exclude_tuple = tuple(exclude)

    matches: dict[str, Path] = {}
    for pattern in include_tuple:
        for path in repo_root.glob(pattern):
            if not path.is_file() or path.suffix != ".md":
                continue
            rel = path.relative_to(repo_root).as_posix()
            if any(fnmatch.fnmatchcase(rel, ex) for ex in exclude_tuple):
                continue
            matches[rel] = path

    return [WalkedFile(rel_path=rel, abs_path=matches[rel]) for rel in sorted(matches)]


__all__ = [
    "DEFAULT_EXCLUDE",
    "DEFAULT_INCLUDE",
    "WalkedFile",
    "walk_repo",
]
