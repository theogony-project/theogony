from __future__ import annotations

import argparse
import re
from pathlib import Path

from theogony.mesh.seeds.wikidata5m.loader import iter_entity_text_pairs_bounded


def _candidate_sentences(text: str, *, max_sentences: int = 2) -> str:
    parts = [part.strip() for part in re.split(r"(?<=[.!?])\s+", text.strip()) if part.strip()]
    return " ".join(parts[:max_sentences])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, default=Path("data/raw/wikidata5m"))
    parser.add_argument("--slice", type=int, default=1000)
    parser.add_argument("--lookup-window-size", type=int, default=4096)
    parser.add_argument("--min-text-len", type=int, default=200)
    parser.add_argument("--pick-index", type=int, default=0)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("tests/mesh/seeds/fixtures/paragraph_smoke1_handoff.txt"),
    )
    args = parser.parse_args()

    candidates = []
    for entity, text in iter_entity_text_pairs_bounded(
        args.data_root / "wikidata5m_entity.txt",
        args.data_root / "wikidata5m_text.txt",
        max_pairs=args.slice,
        lookup_window_size=args.lookup_window_size,
    ):
        alias = entity.aliases[0].strip() if entity.aliases else ""
        if not alias or len(text.description_text) < args.min_text_len:
            continue
        candidates.append((entity.qid, alias, text.description_text))

    if args.pick_index < 0 or args.pick_index >= len(candidates):
        raise SystemExit(
            f"pick-index {args.pick_index} outside candidate range 0..{len(candidates) - 1}"
        )

    qid, alias, description_text = candidates[args.pick_index]
    paragraph = f"{alias} ({qid}) {_candidate_sentences(description_text)}\n"
    args.output.write_text(paragraph, encoding="utf-8")
    print(f"wrote {args.output} from {qid} {alias}")


if __name__ == "__main__":
    main()
