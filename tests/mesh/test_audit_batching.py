"""The audit log batches its per-item writes without losing or reordering them.

One Lance transaction per audit row is affordable for the handful of run-level
entries and ruinous for the per-item ones. Measured inside a real ingest,
`append` cost 269.8 ms per call and was the largest single term in the whole
resolution stage — 22.1 s of 26.5 s for six paragraphs, ten times what identity
linking cost. The same call measures 3.1 ms in isolation, which is why it stayed
invisible until the stage was attributed end to end (PHX-1061).

Two properties matter more than the speed. A staged row is stamped when the
event happened, not when it was written, so the trail keeps its chronology. And
a staged row is never invisible: reads flush first.
"""

from __future__ import annotations

from theogony.mesh.runtime.oneiros_tick import MeshRuntime


def test_staging_defers_the_write(mesh_runtime: MeshRuntime) -> None:
    audit = mesh_runtime.audit
    before = audit.count()

    audit.stage(action="probe", detail={"i": 1})
    assert audit.pending() == 1

    assert audit.flush() == 1
    assert audit.pending() == 0
    assert audit.count() == before + 1


def test_a_staged_row_is_never_invisible_to_a_reader(mesh_runtime: MeshRuntime) -> None:
    """Reads flush first, so no caller can observe a gap."""
    audit = mesh_runtime.audit
    row_id = audit.stage(action="probe", detail={"marker": "visible"})

    ids = {row["id"] for row in audit.list_recent(limit=20)}

    assert row_id in ids
    assert audit.pending() == 0


def test_rows_are_stamped_when_staged_not_when_written(mesh_runtime: MeshRuntime) -> None:
    """The trail records when things happened, not when the buffer drained."""
    audit = mesh_runtime.audit
    first = audit.stage(action="probe", detail={"n": 1})
    second = audit.stage(action="probe", detail={"n": 2})
    audit.flush()

    rows = {row["id"]: row for row in audit.list_recent(limit=20)}
    assert rows[first]["recorded_at"] <= rows[second]["recorded_at"]
    # ULIDs are time-ordered, so staging order survives the batched write.
    assert first < second


def test_staging_auto_flushes_before_the_buffer_grows_unbounded(
    mesh_runtime: MeshRuntime,
) -> None:
    """Staged rows are lost on a hard crash, so the buffer stays bounded."""
    from theogony.mesh.storage.audit import _STAGE_FLUSH_LIMIT

    audit = mesh_runtime.audit
    for i in range(_STAGE_FLUSH_LIMIT):
        audit.stage(action="probe", detail={"i": i})

    assert audit.pending() == 0
    assert audit.count() >= _STAGE_FLUSH_LIMIT


def test_flushing_nothing_is_harmless(mesh_runtime: MeshRuntime) -> None:
    assert mesh_runtime.audit.flush() == 0


def test_immediate_append_still_works(mesh_runtime: MeshRuntime) -> None:
    """Run-level entries keep writing straight through, crash or not."""
    audit = mesh_runtime.audit
    row_id = audit.append(action="run_level", detail={"kind": "immediate"})
    assert row_id in {row["id"] for row in audit.list_recent(limit=20)}
