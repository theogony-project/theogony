"""The substrate's only pointer back to its sources must point at a source (PHX-1103)."""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

from ulid import ULID

from theogony.mesh.runtime.oneiros_tick import MeshRuntime
from theogony.mesh.schemas import ChunkNode, SourceProvenance

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from mesh_repair_chunk_provenance import repaired  # noqa: E402

NOW = datetime(2026, 9, 2, tzinfo=UTC)
SCRATCH = "/private/tmp/claude-501/x/scratchpad/fullread/batch_03.txt"


def _chunk(ref: str, ident: str) -> ChunkNode:
    return ChunkNode(
        id=ULID(),
        born_at=NOW,
        last_fired_at=NOW,
        semantic_vector=[0.1] * 8,
        frame_vector=[0.1] * 4,
        source=SourceProvenance(source_type="text", source_identifier=ident, extracted_at=NOW),
        raw_text_ref=ref,
    )


def test_a_scratch_ref_becomes_a_source_paragraph() -> None:
    node = _chunk(f"{SCRATCH}#p17", SCRATCH)
    fixed = repaired(node, source="gutenberg_348", batch_size=100)
    assert fixed is not None
    assert fixed.raw_text_ref == "gutenberg_348#p317"
    assert fixed.source.source_identifier == "gutenberg_348"
    assert node.raw_text_ref.endswith("#p17"), "the input is not mutated"


def test_a_ref_already_in_the_right_form_is_left_alone() -> None:
    node = _chunk("gutenberg_348#p317", "gutenberg_348")
    assert repaired(node, source="gutenberg_348", batch_size=100) is None


def test_the_store_can_rewrite_its_chunk_tier(tmp_path: Path) -> None:
    runtime = MeshRuntime(tmp_path / "ws", semantic_dim=8, frame_dim=4)
    a, b = _chunk(f"{SCRATCH}#p1", SCRATCH), _chunk("gutenberg_348#p5", "gutenberg_348")
    runtime.nodes.append_chunks([a, b])
    fixed = [repaired(n, source="gutenberg_348", batch_size=100) or n for n in (a, b)]
    runtime.nodes.replace_all_chunks(fixed)
    stored = {str(n.id): n for n in runtime.nodes.iter_chunks()}
    assert stored[str(a.id)].raw_text_ref == "gutenberg_348#p301"
    assert stored[str(b.id)].raw_text_ref == "gutenberg_348#p5"
    assert runtime.nodes.chunk_count() == 2
