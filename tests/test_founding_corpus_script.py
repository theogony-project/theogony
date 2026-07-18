"""Founding-corpus manifest discipline (PHX-1045 / F2): pinned IDs stay unique
and the offline verification logic catches Gutendex metadata drift before any
LLM spend."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "build_founding_mesh.py"
_spec = importlib.util.spec_from_file_location("build_founding_mesh", _SCRIPT)
assert _spec is not None and _spec.loader is not None
founding = importlib.util.module_from_spec(_spec)
sys.modules["build_founding_mesh"] = founding  # dataclasses needs the module registered
_spec.loader.exec_module(founding)


def test_manifest_ids_are_unique_and_pinned() -> None:
    ids = [w.gutenberg_id for w in founding.MANIFEST]
    assert len(ids) == len(set(ids))
    # The founding corpus is pinned — a manifest change is a deliberate act.
    assert set(ids) == {348, 2199, 21765, 26073, 1727}


def test_core_corpus_excludes_optional_works() -> None:
    core = [w for w in founding.MANIFEST if not w.optional]
    assert {w.gutenberg_id for w in core} == {348, 2199, 21765, 26073}


def test_verify_metadata_accepts_matching_gutendex_record() -> None:
    work = founding.MANIFEST[0]  # PG 348 — Hesiod
    metadata = {
        "title": "Hesiod, the Homeric Hymns, and Homerica",
        "authors": [{"name": "Hesiod"}],
    }
    assert founding.verify_metadata(work, metadata) == []


def test_verify_metadata_flags_title_and_author_drift() -> None:
    work = founding.MANIFEST[1]  # PG 2199 — The Iliad, Homer
    metadata = {"title": "A Completely Different Book", "authors": [{"name": "Nobody"}]}
    mismatches = founding.verify_metadata(work, metadata)
    assert len(mismatches) == 2
    assert any("title" in m for m in mismatches)
    assert any("authors" in m for m in mismatches)
