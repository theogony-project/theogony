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
from pathlib import Path

GUTENDEX_BOOK_URL = "https://gutendex.com/books/{book_id}"
GUTENBERG_TEXT_URL = "https://www.gutenberg.org/cache/epub/{book_id}/pg{book_id}.txt"
GUTENBERG_END_MARKER = "*** END OF THE PROJECT GUTENBERG"
DEFAULT_MESH_ROOT = "data/mesh-founding"
DEFAULT_RAW_DIR = "data/raw/founding"
PILOT_PARAGRAPHS = 50


@dataclass(frozen=True)
class CorpusWork:
    """One pinned Project Gutenberg volume of the founding corpus.

    ``start_marker`` is the first line of the actual work inside the volume —
    everything before it (Gutenberg boilerplate, prefaces, scholarly
    introductions; 2,452 lines in PG 348!) is cut before ingestion so Kadmos
    reads the primary source, not the front matter. Markers verified against
    the live pg{id}.txt files on 2026-07-14.
    """

    gutenberg_id: int
    label: str
    expected_title_fragment: str
    expected_author_fragment: str
    start_marker: str
    optional: bool = False


# IDs verified against live Gutendex on 2026-07-14 (see PHX-1045 / plan §corpus).
MANIFEST: tuple[CorpusWork, ...] = (
    CorpusWork(
        gutenberg_id=348,
        label="Hesiod — Theogony + Homeric Hymns (Evelyn-White)",
        expected_title_fragment="hesiod",
        expected_author_fragment="hesiod",
        start_marker="THE THEOGONY",  # skips preface/introduction/Works and Days
    ),
    CorpusWork(
        gutenberg_id=2199,
        label="Homer — The Iliad (Butler, prose)",
        expected_title_fragment="iliad",
        expected_author_fragment="homer",
        start_marker="BOOK I.",
    ),
    CorpusWork(
        gutenberg_id=21765,
        label="Ovid — Metamorphoses, Books I-VII (Riley, prose)",
        expected_title_fragment="metamorphoses",
        expected_author_fragment="ovid",
        start_marker="BOOK THE FIRST.",  # "BOOK I." earlier in the file is the contents list
    ),
    CorpusWork(
        gutenberg_id=26073,
        label="Ovid — Metamorphoses, Books VIII-XV (Riley, prose)",
        expected_title_fragment="metamorphoses",
        expected_author_fragment="ovid",
        start_marker="BOOK THE EIGHTH.",
    ),
    CorpusWork(
        gutenberg_id=1727,
        label="Homer — The Odyssey (Butler, prose)",
        expected_title_fragment="odyssey",
        expected_author_fragment="homer",
        start_marker="BOOK I",
        optional=True,
    ),
)


def slice_work_text(work: CorpusWork, raw_text: str) -> str | None:
    """Cut the volume to the actual work: from the *last standalone* occurrence
    of ``start_marker`` (a line equal to the marker — section headings stand
    alone; earlier hits are the table of contents) to the Gutenberg end marker.
    Returns None (structured failure) when either marker is missing."""
    lines = raw_text.splitlines(keepends=True)
    heading_idx = None
    for i, line in enumerate(lines):
        if line.strip() == work.start_marker:
            heading_idx = i
    if heading_idx is None:
        return None
    body = "".join(lines[heading_idx:])
    end = body.find(GUTENBERG_END_MARKER)
    if end < 0:
        return None
    return body[:end].strip()


def download_text(work: CorpusWork, raw_dir: Path) -> Path:
    """Fetch (and cache) the raw plain-text volume."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / f"pg{work.gutenberg_id}.txt"
    if path.exists() and path.stat().st_size > 0:
        return path
    url = GUTENBERG_TEXT_URL.format(book_id=work.gutenberg_id)
    request = urllib.request.Request(url, headers={"User-Agent": "theogony-founding-corpus"})
    with urllib.request.urlopen(request, timeout=120) as response:  # noqa: S310
        path.write_bytes(response.read())
    return path


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


def ingest_work(work: CorpusWork, *, mesh_root: str, raw_dir: Path, paragraphs: int) -> bool:
    print(f"\n=== {work.label} (PG {work.gutenberg_id}) ===")
    try:
        raw_path = download_text(work, raw_dir)
    except Exception as exc:  # noqa: BLE001 — structured failure, no ingest
        print(f"FAIL  PG {work.gutenberg_id}: download failed: {exc}")
        return False
    sliced = slice_work_text(work, raw_path.read_text(encoding="utf-8"))
    if sliced is None:
        print(f"FAIL  PG {work.gutenberg_id}: start marker {work.start_marker!r} not found")
        return False
    sliced_path = raw_dir / f"pg{work.gutenberg_id}_{work.start_marker.split()[0].lower()}.txt"
    sliced_path.write_text(sliced, encoding="utf-8")
    cmd = [
        "theogony",
        "mesh",
        "ingest",
        str(sliced_path),
        "--text-file",
        "--source-type",
        "gutenberg",
        "--title",
        work.label,
        "--anchor",
        f"https://www.gutenberg.org/ebooks/{work.gutenberg_id}",
        "--paragraphs",
        str(paragraphs),
        "--root",
        mesh_root,
    ]
    print("$", " ".join(cmd))
    completed = subprocess.run(  # noqa: S603 — fixed argv, no shell
        cmd, check=False, capture_output=True, text=True
    )
    sys.stdout.write(completed.stdout)
    sys.stderr.write(completed.stderr)
    if completed.returncode != 0:
        print(f"FAIL  PG {work.gutenberg_id}: ingest exited {completed.returncode}")
        return False
    # The CLI exits 0 even when the reader emits verdict="failed" (e.g. every
    # LLM call 400s) — surfaced by the PHX-1045 Sonnet-5 pilot. Treat it as
    # the structured failure it is.
    if '"failed"' in completed.stdout:
        print(f"FAIL  PG {work.gutenberg_id}: ingest verdict is 'failed' (see run report)")
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
    parser.add_argument("--raw-dir", default=DEFAULT_RAW_DIR, help="Cache dir for raw texts.")
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
    raw_dir = Path(args.raw_dir)
    failures = [
        w
        for w in works
        if not ingest_work(w, mesh_root=args.mesh_root, raw_dir=raw_dir, paragraphs=paragraphs)
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
