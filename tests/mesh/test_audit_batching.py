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


def test_recent_rows_come_back_newest_first(mesh_runtime: MeshRuntime) -> None:
    """Ordering moved into the store; the answer must not move with it."""
    audit = mesh_runtime.audit
    ids = [audit.append(action="ordered", detail={"n": i}) for i in range(5)]

    rows = audit.list_recent(limit=3)

    assert [r["id"] for r in rows] == list(reversed(ids))[:3]
    assert len(rows) == 3


def test_recent_respects_a_limit_larger_than_the_table(mesh_runtime: MeshRuntime) -> None:
    audit = mesh_runtime.audit
    audit.append(action="only", detail={})
    assert len(audit.list_recent(limit=100)) == audit.count()


def test_pruning_the_audit_log_keeps_every_row(mesh_runtime: MeshRuntime) -> None:
    """The log is the substrate's record; only its storage snapshots go.

    This table was the one no maintenance pass touched, and it is the most
    written of them all. At 21,219 rows it had 5,915 versions and reading the
    ten newest cost 266.6 ms — 2.1 ms once pruned (PHX-1062).
    """
    from datetime import timedelta

    audit = mesh_runtime.audit
    ids = [audit.append(action="kept", detail={"n": i}) for i in range(20)]
    before_versions = len(audit._table.list_versions())

    removed = audit.prune_history(retention=timedelta(0))

    assert removed > 0
    assert len(audit._table.list_versions()) < before_versions
    assert audit.count() == len(ids)
    assert {r["id"] for r in audit.list_recent(limit=50)} == set(ids)


def test_pruning_flushes_staged_rows_first(mesh_runtime: MeshRuntime) -> None:
    """A stamped row must not be lost to the pass that tidies up around it."""
    from datetime import timedelta

    audit = mesh_runtime.audit
    row_id = audit.stage(action="staged", detail={"marker": "survives"})
    assert audit.pending() == 1

    audit.prune_history(retention=timedelta(0))

    assert audit.pending() == 0
    assert row_id in {r["id"] for r in audit.list_recent(limit=50)}


def test_the_tick_prunes_the_audit_log_too(mesh_runtime: MeshRuntime) -> None:
    for i in range(20):
        mesh_runtime.audit.append(action="tick-probe", detail={"n": i})

    result = mesh_runtime.run_minimal_tick()

    assert "mesh_audit" in result.versions_pruned
    assert result.versions_pruned["mesh_audit"] > 0
