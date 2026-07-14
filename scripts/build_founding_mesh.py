#!/usr/bin/env python3
"""Build the founding mesh: the Greek-mythology corpus read by Kadmos v2 (PHX-1045 / F2).

Drives the production ingest path (``theogony mesh ingest``) over a pinned,
Gutendex-verified manifest of primary sources. Two modes:

  --verify-only     check the manifest against live Gutendex metadata and exit
                    (no LLM spend; run this first)
  --pilot           read ~50 paragraphs per source (model-decision pilot, F3)
  (default)         full read of every non-optional source

The mesh root defaults to ``data/mesh-founding`` so the founding mesh never
mixes with ``data/mesh-wiki-*`` seeds. Title/author verification failures are
structured failures: nothing is ingested if any manifest entry mismatches.

Embedder alignment (PHX-1031): ``mesh ingest`` reads the embedder from
``THEOGONY_EMBEDDING__MODEL_ID`` / ``THEOGONY_EMBEDDING__DIM`` — keep these
identical between the pilot and the full read, or Tier-2/Tier-3 linking breaks.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.request
from dataclasses import dataclass

GUTENDEX_BOOK_URL = "https://gutendex.com/books/{book_id}"
DEFAULT_MESH_ROOT = "data/mesh-founding"
PILOT_PARAGRAPHS = 50


@dataclass(frozen=True)
class CorpusWork:
    """One pinned Project Gutenberg volume of the founding corpus."""

    gutenberg_id: int
    label: str
    expected_title_fragment: str
    expected_author_fragment: str
    optional: bool = False


# IDs verified against live Gutendex on 2026-07-14 (see PHX-1045 / plan §corpus).
MANIFEST: tuple[CorpusWork, ...] = (
    CorpusWork(
        gutenberg_id=348,
        label="Hesiod — Theogony, Works and Days + Homeric Hymns (Evelyn-White)",
        expected_title_fragment="hesiod",
        expected_author_fragment="hesiod",
    ),
    CorpusWork(
        gutenberg_id=2199,
        label="Homer — The Iliad (Butler, prose)",
        expected_title_fragment="iliad",
        expected_author_fragment="homer",
    ),
    CorpusWork(
        gutenberg_id=21765,
        label="Ovid — Metamorphoses, Books I-VII (Riley, prose)",
        expected_title_fragment="metamorphoses",
        expected_author_fragment="ovid",
    ),
    CorpusWork(
        gutenberg_id=26073,
        label="Ovid — Metamorphoses, Books VIII-XV (Riley, prose)",
        expected_title_fragment="metamorphoses",
        expected_author_fragment="ovid",
    ),
    CorpusWork(
        gutenberg_id=1727,
        label="Homer — The Odyssey (Butler, prose)",
        expected_title_fragment="odyssey",
        expected_author_fragment="homer",
        optional=True,
    ),
)


def verify_metadata(work: CorpusWork, metadata: dict) -> list[str]:
    """Return the list of mismatch reasons between a manifest entry and Gutendex
    metadata (empty = verified). Pure function so it is testable offline."""
    mismatches: list[str] = []
    title = str(metadata.get("title", "")).lower()
    authors = " / ".join(a.get("name", "") for a in metadata.get("authors", [])).lower()
    if work.expected_title_fragment.lower() not in title:
        mismatches.append(
            f"title {metadata.get('title')!r} does not contain {work.expected_title_fragment!r}"
        )
    if work.expected_author_fragment.lower() not in authors:
        mismatches.append(f"authors {authors!r} do not contain {work.expected_author_fragment!r}")
    return mismatches


def fetch_gutendex_metadata(book_id: int) -> dict:
    url = GUTENDEX_BOOK_URL.format(book_id=book_id)
    request = urllib.request.Request(url, headers={"User-Agent": "theogony-founding-corpus"})
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
        payload: dict = json.loads(response.read().decode("utf-8"))
    return payload


def verify_manifest(works: list[CorpusWork]) -> bool:
    ok = True
    for work in works:
        try:
            metadata = fetch_gutendex_metadata(work.gutenberg_id)
        except Exception as exc:  # noqa: BLE001 — report and continue verifying the rest
            print(f"FAIL  PG {work.gutenberg_id}: Gutendex fetch failed: {exc}")
            ok = False
            continue
        mismatches = verify_metadata(work, metadata)
        if mismatches:
            ok = False
            for reason in mismatches:
                print(f"FAIL  PG {work.gutenberg_id}: {reason}")
        else:
            print(f"ok    PG {work.gutenberg_id}: {metadata.get('title')}")
    return ok


def ingest_work(work: CorpusWork, *, mesh_root: str, paragraphs: int) -> bool:
    cmd = [
        "theogony",
        "mesh",
        "ingest",
        str(work.gutenberg_id),
        "--paragraphs",
        str(paragraphs),
        "--root",
        mesh_root,
    ]
    print(f"\n=== {work.label} (PG {work.gutenberg_id}) ===")
    print("$", " ".join(cmd))
    completed = subprocess.run(cmd, check=False)  # noqa: S603 — fixed argv, no shell
    if completed.returncode != 0:
        print(f"FAIL  PG {work.gutenberg_id}: ingest exited {completed.returncode}")
        return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-only", action="store_true", help="Check manifest, no ingest.")
    parser.add_argument(
        "--pilot", action="store_true", help=f"{PILOT_PARAGRAPHS} paragraphs/source."
    )
    parser.add_argument("--paragraphs", type=int, default=0, help="Override cap (0 = all).")
    parser.add_argument("--mesh-root", default=DEFAULT_MESH_ROOT)
    parser.add_argument("--include-optional", action="store_true", help="Include the Odyssey.")
    parser.add_argument("--only", type=int, default=None, help="Run a single Gutenberg id.")
    args = parser.parse_args()

    works = [w for w in MANIFEST if args.include_optional or not w.optional]
    if args.only is not None:
        works = [w for w in MANIFEST if w.gutenberg_id == args.only]
        if not works:
            print(f"FAIL  PG {args.only} is not in the manifest")
            return 2

    print(f"Founding corpus: {len(works)} work(s), mesh root {args.mesh_root!r}")
    if not verify_manifest(works):
        print("\nManifest verification FAILED — nothing was ingested.")
        return 2
    if args.verify_only:
        print("\nManifest verified. Re-run without --verify-only to ingest.")
        return 0

    paragraphs = args.paragraphs or (PILOT_PARAGRAPHS if args.pilot else 0)
    failures = [
        w for w in works if not ingest_work(w, mesh_root=args.mesh_root, paragraphs=paragraphs)
    ]
    print(
        f"\nDone: {len(works) - len(failures)}/{len(works)} works ingested into {args.mesh_root!r}"
    )
    if failures:
        for w in failures:
            print(f"  failed: PG {w.gutenberg_id} — {w.label}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
