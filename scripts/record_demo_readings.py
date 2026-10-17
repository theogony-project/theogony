#!/usr/bin/env python
"""Record Kadmos readings of a text, so a mesh can be rebuilt from them without a key.

    THEOGONY_LLM__PROVIDER=deepseek THEOGONY_LLM__MODEL_ID=deepseek-chat \\
        python scripts/record_demo_readings.py src/theogony/seeds/hesiod_theogony.txt \\
            --out src/theogony/seeds/hesiod_theogony_readings.jsonl.gz \\
            --title "Hesiod, Theogony (Hugh G. Evelyn-White, 1914)" \\
            --source https://www.gutenberg.org/ebooks/348

One language-model call per paragraph, with exactly the prompt the shipped
reader sends (`kadmos_v2.paragraph_prompt`, `SYSTEM_PROMPT`, the same schema
and temperature). The reply is normalised and validated the way the reader
does it and stored under `reading_key(paragraph)`, the key the replay
provider looks a paragraph up by. What is recorded is what Kadmos would have
read; what `theogony mesh demo` then writes is what the reader writes
(PHX-1112, from the PHX-1110 replay).

The file opens with a `meta` row — model, date, counts, cost — and every
reading row carries the `model_id` that actually answered it, so a fallback
provider stepping in for one paragraph is on the record. Exit code 1 if any
paragraph has no reading after three attempts: a demo corpus with holes
would replay as a mesh with silent gaps.
"""

from __future__ import annotations

import argparse
import asyncio
import gzip
import json
import sys
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from theogony.agents.factory import build_llm_from_settings
from theogony.config.settings import Settings
from theogony.mesh.ingestion.kadmos_v2 import SYSTEM_PROMPT, paragraph_prompt
from theogony.mesh.ingestion.reading_schemas import (
    ParagraphReadingOutput,
    normalize_reading_payload,
)
from theogony.mesh.ingestion.replay import paragraphs_of, reading_key


async def read_one(
    llm: Any, paragraph: str, *, attempts: int = 3
) -> tuple[dict[str, Any] | None, str, float]:
    """One paragraph's reading, the model that gave it, and what it cost."""
    cost = 0.0
    model_id = ""
    for attempt in range(attempts):
        try:
            # Mirrors MeshParagraphReader._read_paragraph, argument for argument.
            result = await llm.complete(
                prompt=paragraph_prompt(paragraph),
                system=SYSTEM_PROMPT,
                json_schema=ParagraphReadingOutput.model_json_schema(),
                temperature=0.1,
                timeout_s=45,
            )
            cost += float(getattr(result, "cost_eur", 0.0) or 0.0)
            model_id = str(getattr(result, "model_id", "") or "")
            payload = normalize_reading_payload(json.loads(result.text))
            return ParagraphReadingOutput.model_validate(payload).model_dump(), model_id, cost
        except Exception as exc:  # noqa: BLE001 - retried, then recorded as a miss
            print(
                f"  attempt {attempt + 1} failed: {type(exc).__name__}: {str(exc)[:120]}",
                file=sys.stderr,
            )
            await asyncio.sleep(2.0 * (attempt + 1))
    return None, model_id, cost


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("corpus", type=Path, help="plain text; paragraphs separated by blank lines")
    ap.add_argument("--out", type=Path, required=True, help="readings file (.jsonl or .jsonl.gz)")
    ap.add_argument("--concurrency", type=int, default=6)
    ap.add_argument("--title", default="", help="recorded in the meta row")
    ap.add_argument("--source", default="", help="recorded in the meta row")
    args = ap.parse_args()

    settings = Settings()
    llm = build_llm_from_settings(settings)
    text = args.corpus.read_text(encoding="utf-8")
    paragraphs = paragraphs_of(text)
    print(f"{len(paragraphs)} paragraphs; provider {getattr(llm, 'model_id', '?')}")

    sem = asyncio.Semaphore(max(1, args.concurrency))
    started = time.perf_counter()
    done = 0
    readings: dict[str, tuple[dict[str, Any] | None, str]] = {}
    cost_total = 0.0

    async def one(paragraph: str) -> None:
        nonlocal done, cost_total
        async with sem:
            reading, model_id, cost = await read_one(llm, paragraph)
            readings[reading_key(paragraph)] = (reading, model_id)
            cost_total += cost
            done += 1
            if done % 10 == 0 or done == len(paragraphs):
                elapsed = time.perf_counter() - started
                print(
                    f"  {done}/{len(paragraphs)}  {elapsed:.0f} s  {cost_total:.4f} EUR", flush=True
                )

    await asyncio.gather(*(one(p) for p in paragraphs))

    rows = [(reading_key(p), *readings[reading_key(p)]) for p in paragraphs]
    misses = [k for k, reading, _ in rows if reading is None]
    kept = [(k, reading, model) for k, reading, model in rows if reading is not None]
    models = Counter(model for _, _, model in kept)
    stances = Counter(r.get("stance", "?") for _, reading, _ in kept for r in reading["relations"])
    kinds = Counter(
        r.get("relation_kind", "?") for _, reading, _ in kept for r in reading["relations"]
    )
    meta = {
        "title": args.title,
        "source": args.source,
        "recorded_at": datetime.now(UTC).isoformat(),
        "provider": getattr(llm, "model_id", "?"),
        "model_ids": dict(models),
        "paragraphs": len(paragraphs),
        "readings": len(kept),
        "concepts": sum(len(reading["concepts"]) for _, reading, _ in kept),
        "relations": sum(len(reading["relations"]) for _, reading, _ in kept),
        "relation_stances": dict(stances.most_common()),
        "relation_kinds": dict(kinds.most_common()),
        "cost_eur": round(cost_total, 4),
        "wall_s": round(time.perf_counter() - started, 1),
        "prompt": "theogony.mesh.ingestion.kadmos_v2.paragraph_prompt + SYSTEM_PROMPT, verbatim",
        "key": "theogony.mesh.ingestion.replay.reading_key of the stripped paragraph",
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    opener = gzip.open if args.out.suffix == ".gz" else open
    with opener(args.out, "wt", encoding="utf-8") as fh:
        fh.write(json.dumps({"meta": meta}, ensure_ascii=False) + "\n")
        for key, reading, model in kept:
            fh.write(
                json.dumps({"key": key, "model_id": model, "reading": reading}, ensure_ascii=False)
                + "\n"
            )
    print(json.dumps(meta, indent=2, ensure_ascii=False))
    print(f"misses: {len(misses)}  -> {args.out} ({args.out.stat().st_size} bytes)")
    return 1 if misses else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
