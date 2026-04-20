"""
Regenerate the bundled ``pantheon_self`` Chronicle dump.

Runnable two ways:

1. As a module: ``python -m theogony.docs_ingest.regenerate``
2. As a Python API: :func:`regenerate` for tests / CI scripts

Defaults: walks the **current repository root** (resolved by climbing
parents from this file until ``pyproject.toml`` is found), embeds with
the project default embedder (``BAAI/bge-small-en-v1.5``), and writes
to ``src/theogony/seeds/pantheon_self.jsonl.gz``.

This is **project-developer code**, not end-user code. End users get
the pre-built dump shipped in the wheel and import it via
``theogony seed`` — they never need to call this module.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from theogony.config.logging import get_logger, setup_logging
from theogony.config.settings import Settings
from theogony.docs_ingest.dump import write_dump
from theogony.docs_ingest.pipeline import RepoSnapshot, build_chronicle
from theogony.extraction.embedding import LocalSentenceTransformerEmbedder

log = get_logger("docs_ingest.regenerate")

#: Default output path relative to the repo root.
DEFAULT_OUTPUT_REL = Path("src/theogony/seeds/pantheon_self.jsonl.gz")


def _find_repo_root(start: Path | None = None) -> Path:
    """Climb parent directories until ``pyproject.toml`` is found."""
    here = (start or Path(__file__)).resolve()
    for candidate in (here, *here.parents):
        if (candidate / "pyproject.toml").exists():
            return candidate
    raise RuntimeError("could not find repo root (no pyproject.toml in any parent directory)")


def regenerate(
    *,
    repo_root: Path | None = None,
    output_path: Path | None = None,
    no_embed: bool = False,
) -> Path:
    """Run the docs pipeline against ``repo_root`` and write the dump.

    Returns the resolved ``output_path`` so CI can verify the file
    exists. ``no_embed=True`` skips the embedder — useful for fast
    schema-only test runs that do not need vectors.
    """
    repo_root = repo_root or _find_repo_root()
    output_path = output_path or (repo_root / DEFAULT_OUTPUT_REL)

    settings = Settings()
    setup_logging(settings)

    embedder: LocalSentenceTransformerEmbedder | None = None
    if not no_embed:
        embedder = LocalSentenceTransformerEmbedder(
            model_id=settings.embedding.model_id,
            dim=settings.embedding.dim,
        )

    snapshot = RepoSnapshot(repo_root=repo_root)

    last_progress = [0]

    def _progress(done: int, total: int) -> None:
        # Log every 10% so a 200-node embed is six log lines, not 200.
        pct = int(100 * done / max(total, 1))
        if pct - last_progress[0] >= 10 or done == total:
            last_progress[0] = pct
            log.info("embedding %d/%d (%d%%)", done, total, pct)

    log.info(
        "regenerate: repo_root=%s output=%s embedder=%s",
        repo_root,
        output_path,
        embedder.model_id if embedder else "<disabled>",
    )
    chronicle = build_chronicle(snapshot, embedder=embedder, progress=_progress)
    log.info(
        "regenerate: extracted %d nodes / %d edges",
        len(chronicle.nodes),
        len(chronicle.edges),
    )

    write_dump(
        chronicle,
        output_path,
        metadata={
            "source": "theogony-self",
            "generator": "theogony.docs_ingest.regenerate",
        },
    )
    log.info("regenerate: wrote %s", output_path)
    return output_path


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m theogony.docs_ingest.regenerate",
        description=(
            "Regenerate the bundled pantheon_self Chronicle dump from "
            "the current repository's docs / prompts / agent files."
        ),
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Repository root to walk (default: auto-detect from this file).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help=(
            "Output dump path (default: src/theogony/seeds/pantheon_self.jsonl.gz "
            "under the resolved repo root)."
        ),
    )
    parser.add_argument(
        "--no-embed",
        action="store_true",
        help="Skip the embedder (vectors will be empty in the output).",
    )
    args = parser.parse_args(argv)

    output = regenerate(
        repo_root=args.repo_root,
        output_path=args.output,
        no_embed=args.no_embed,
    )
    print(f"wrote {output}")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry only
    sys.exit(main())
