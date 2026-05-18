"""Streaming readers for the four wikidata5m text files."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

from theogony.config.logging import get_logger

log = get_logger("mesh.seeds.wikidata5m.loader")

MalformedCallback = Callable[[str, int, str, str], None]
MissingTextCallback = Callable[[str], None]

_QID_RE = re.compile(r"^[QP](\d+)$")


@dataclass(frozen=True)
class EntityRecord:
    qid: str
    aliases: list[str]


@dataclass(frozen=True)
class TextRecord:
    qid: str
    description_text: str


@dataclass(frozen=True)
class RelationRecord:
    pid: str
    aliases: list[str]


@dataclass(frozen=True)
class TripletRecord:
    subject_qid: str
    predicate_pid: str
    object_qid: str


def _numeric_id(identifier: str) -> int:
    match = _QID_RE.match(identifier)
    if match is None:
        return 0
    return int(match.group(1))


def _emit_malformed(
    *,
    file_name: str,
    line_number: int,
    reason: str,
    raw_line: str,
    on_malformed: MalformedCallback | None,
    log_warning: bool = True,
) -> None:
    if log_warning:
        log.warning("%s:%d malformed row: %s", file_name, line_number, reason)
    if on_malformed is not None:
        on_malformed(file_name, line_number, reason, raw_line)


def _iter_lines(path: Path) -> Iterator[tuple[int, str]]:
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            yield line_number, raw_line.rstrip("\n")


def iter_entity_records(
    path: Path,
    *,
    on_malformed: MalformedCallback | None = None,
) -> Iterator[EntityRecord]:
    for line_number, raw_line in _iter_lines(path):
        if not raw_line.strip():
            _emit_malformed(
                file_name=path.name,
                line_number=line_number,
                reason="blank line",
                raw_line=raw_line,
                on_malformed=on_malformed,
            )
            continue
        parts = raw_line.split("\t")
        qid = parts[0].strip()
        aliases = [alias.strip() for alias in parts[1:] if alias.strip()]
        if not qid.startswith("Q"):
            _emit_malformed(
                file_name=path.name,
                line_number=line_number,
                reason="missing Q-ID",
                raw_line=raw_line,
                on_malformed=on_malformed,
            )
            continue
        if not aliases:
            _emit_malformed(
                file_name=path.name,
                line_number=line_number,
                reason="missing aliases",
                raw_line=raw_line,
                on_malformed=on_malformed,
            )
            continue
        yield EntityRecord(qid=qid, aliases=aliases)


def iter_text_records(
    path: Path,
    *,
    on_malformed: MalformedCallback | None = None,
) -> Iterator[TextRecord]:
    for line_number, raw_line in _iter_lines(path):
        if not raw_line.strip():
            _emit_malformed(
                file_name=path.name,
                line_number=line_number,
                reason="blank line",
                raw_line=raw_line,
                on_malformed=on_malformed,
            )
            continue
        qid, separator, description_text = raw_line.partition("\t")
        if separator == "" or not qid.startswith("Q"):
            _emit_malformed(
                file_name=path.name,
                line_number=line_number,
                reason="missing Q-ID/text payload",
                raw_line=raw_line,
                on_malformed=on_malformed,
            )
            continue
        if not description_text.strip():
            _emit_malformed(
                file_name=path.name,
                line_number=line_number,
                reason="empty text payload",
                raw_line=raw_line,
                on_malformed=on_malformed,
            )
            continue
        yield TextRecord(qid=qid.strip(), description_text=description_text.strip())


def iter_relation_records(
    path: Path,
    *,
    on_malformed: MalformedCallback | None = None,
) -> Iterator[RelationRecord]:
    for line_number, raw_line in _iter_lines(path):
        if not raw_line.strip():
            _emit_malformed(
                file_name=path.name,
                line_number=line_number,
                reason="blank line",
                raw_line=raw_line,
                on_malformed=on_malformed,
            )
            continue
        parts = raw_line.split("\t")
        pid = parts[0].strip()
        aliases = [alias.strip() for alias in parts[1:] if alias.strip()]
        if not pid.startswith("P"):
            _emit_malformed(
                file_name=path.name,
                line_number=line_number,
                reason="missing P-ID",
                raw_line=raw_line,
                on_malformed=on_malformed,
            )
            continue
        if not aliases:
            _emit_malformed(
                file_name=path.name,
                line_number=line_number,
                reason="missing aliases",
                raw_line=raw_line,
                on_malformed=on_malformed,
            )
            continue
        yield RelationRecord(pid=pid, aliases=aliases)


def iter_triplet_records(
    path: Path,
    *,
    on_malformed: MalformedCallback | None = None,
) -> Iterator[TripletRecord]:
    for line_number, raw_line in _iter_lines(path):
        if not raw_line.strip():
            _emit_malformed(
                file_name=path.name,
                line_number=line_number,
                reason="blank line",
                raw_line=raw_line,
                on_malformed=on_malformed,
            )
            continue
        parts = [part.strip() for part in raw_line.split("\t")]
        if len(parts) != 3:
            _emit_malformed(
                file_name=path.name,
                line_number=line_number,
                reason="expected subject, predicate, object",
                raw_line=raw_line,
                on_malformed=on_malformed,
            )
            continue
        subject_qid, predicate_pid, object_qid = parts
        if not subject_qid.startswith("Q") or not object_qid.startswith("Q"):
            _emit_malformed(
                file_name=path.name,
                line_number=line_number,
                reason="triplet endpoint missing Q-ID",
                raw_line=raw_line,
                on_malformed=on_malformed,
            )
            continue
        if not predicate_pid.startswith("P"):
            _emit_malformed(
                file_name=path.name,
                line_number=line_number,
                reason="triplet predicate missing P-ID",
                raw_line=raw_line,
                on_malformed=on_malformed,
            )
            continue
        yield TripletRecord(
            subject_qid=subject_qid,
            predicate_pid=predicate_pid,
            object_qid=object_qid,
        )


def iter_triplet_records_for_qids(
    path: Path,
    qids: set[str],
    *,
    max_triplets: int = 0,
    on_malformed: MalformedCallback | None = None,
) -> Iterator[TripletRecord]:
    yielded = 0
    for record in iter_triplet_records(path, on_malformed=on_malformed):
        if record.subject_qid not in qids or record.object_qid not in qids:
            continue
        yield record
        yielded += 1
        if max_triplets > 0 and yielded >= max_triplets:
            break


def load_relation_aliases(
    path: Path,
    *,
    on_malformed: MalformedCallback | None = None,
) -> dict[str, list[str]]:
    return {
        relation.pid: relation.aliases
        for relation in iter_relation_records(path, on_malformed=on_malformed)
    }


def load_qid_selection_file(path: Path) -> list[str]:
    """Load Q-IDs from a smoke selection file (comments and optional degree column)."""
    qids: list[str] = []
    with path.open(encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            qid = line.split("\t", 1)[0].strip()
            if qid.startswith("Q"):
                qids.append(qid)
    return qids


def load_entity_lookup(
    path: Path,
    qids: Iterable[str],
    *,
    on_malformed: MalformedCallback | None = None,
) -> dict[str, EntityRecord]:
    requested_qids = {qid.strip() for qid in qids if qid.strip()}
    if not requested_qids:
        return {}

    matches: dict[str, EntityRecord] = {}
    for record in iter_entity_records(path, on_malformed=on_malformed):
        if record.qid not in requested_qids or record.qid in matches:
            continue
        matches[record.qid] = record
        if len(matches) >= len(requested_qids):
            break
    return matches


def iter_entity_text_pairs_for_qids(
    entity_path: Path,
    text_path: Path,
    qids: Iterable[str],
    *,
    on_malformed: MalformedCallback | None = None,
    on_missing_text: MissingTextCallback | None = None,
) -> Iterator[tuple[EntityRecord, TextRecord]]:
    ordered_qids = [qid.strip() for qid in qids if qid.strip()]
    if not ordered_qids:
        return

    requested_qids = set(ordered_qids)
    entity_lookup = load_entity_lookup(
        entity_path,
        requested_qids,
        on_malformed=on_malformed,
    )
    text_lookup = load_text_lookup(
        text_path,
        requested_qids,
        on_malformed=on_malformed,
    )
    for qid in ordered_qids:
        entity = entity_lookup.get(qid)
        if entity is None:
            _emit_malformed(
                file_name=entity_path.name,
                line_number=0,
                reason=f"entity row missing for selected {qid}",
                raw_line=qid,
                on_malformed=on_malformed,
                log_warning=False,
            )
            continue
        text_record = text_lookup.get(qid)
        if text_record is None:
            if on_missing_text is not None:
                on_missing_text(qid)
            continue
        yield entity, text_record


def load_text_lookup(
    path: Path,
    qids: Iterable[str],
    *,
    on_malformed: MalformedCallback | None = None,
) -> dict[str, TextRecord]:
    requested_qids = {qid.strip() for qid in qids if qid.strip()}
    if not requested_qids:
        return {}

    matches: dict[str, TextRecord] = {}
    for record in iter_text_records(path, on_malformed=on_malformed):
        if record.qid not in requested_qids or record.qid in matches:
            continue
        matches[record.qid] = record
        if len(matches) >= len(requested_qids):
            break
    return matches


def iter_entity_text_pairs_bounded(
    entity_path: Path,
    text_path: Path,
    *,
    max_pairs: int,
    lookup_window_size: int,
    on_malformed: MalformedCallback | None = None,
    on_missing_text: MissingTextCallback | None = None,
) -> Iterator[tuple[EntityRecord, TextRecord]]:
    if max_pairs <= 0:
        raise ValueError("max_pairs must be > 0")
    if lookup_window_size <= 0:
        raise ValueError("lookup_window_size must be > 0")

    entity_iter = iter(iter_entity_records(entity_path, on_malformed=on_malformed))
    yielded = 0

    while yielded < max_pairs:
        window: list[EntityRecord] = []
        while len(window) < lookup_window_size:
            entity = next(entity_iter, None)
            if entity is None:
                break
            window.append(entity)
        if not window:
            return

        text_lookup = load_text_lookup(
            text_path,
            (entity.qid for entity in window),
            on_malformed=on_malformed,
        )
        for entity in window:
            text_record = text_lookup.get(entity.qid)
            if text_record is None:
                if on_missing_text is not None:
                    on_missing_text(entity.qid)
                continue
            yield entity, text_record
            yielded += 1
            if yielded >= max_pairs:
                return


def iter_entity_text_pairs(
    entity_path: Path,
    text_path: Path,
    *,
    on_malformed: MalformedCallback | None = None,
) -> Iterator[tuple[EntityRecord, TextRecord]]:
    entity_iter = iter(iter_entity_records(entity_path, on_malformed=on_malformed))
    text_iter = iter(iter_text_records(text_path, on_malformed=on_malformed))
    entity = next(entity_iter, None)
    text = next(text_iter, None)

    while entity is not None or text is not None:
        if entity is None and text is not None:
            _emit_malformed(
                file_name=text_path.name,
                line_number=0,
                reason=f"text row without matching entity for {text.qid}",
                raw_line=text.qid,
                on_malformed=on_malformed,
                log_warning=False,
            )
            text = next(text_iter, None)
            continue
        if text is None and entity is not None:
            _emit_malformed(
                file_name=entity_path.name,
                line_number=0,
                reason=f"entity row without matching text for {entity.qid}",
                raw_line=entity.qid,
                on_malformed=on_malformed,
                log_warning=False,
            )
            entity = next(entity_iter, None)
            continue
        assert entity is not None
        assert text is not None
        entity_key = _numeric_id(entity.qid)
        text_key = _numeric_id(text.qid)
        if entity.qid == text.qid:
            yield entity, text
            entity = next(entity_iter, None)
            text = next(text_iter, None)
            continue
        if entity_key <= text_key:
            _emit_malformed(
                file_name=entity_path.name,
                line_number=0,
                reason=f"entity row without matching text for {entity.qid}",
                raw_line=entity.qid,
                on_malformed=on_malformed,
                log_warning=False,
            )
            entity = next(entity_iter, None)
            continue
        _emit_malformed(
            file_name=text_path.name,
            line_number=0,
            reason=f"text row without matching entity for {text.qid}",
            raw_line=text.qid,
            on_malformed=on_malformed,
            log_warning=False,
        )
        text = next(text_iter, None)
