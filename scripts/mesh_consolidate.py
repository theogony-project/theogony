#!/usr/bin/env python
"""Run one Oneiros consolidation pass over a mesh (S5).

    scripts/mesh_consolidate.py --root data/mesh-founding --dry-run
    scripts/mesh_consolidate.py --root data/mesh-founding

Without `--dry-run` this **rewrites the substrate**: it merges entity candidates
that an LLM confirms are the same entity, rewires their edges onto the survivor,
regenerates the survivor's description, and deletes the absorbed rows. Copy the
workspace first. The absorbed ids survive only in the `mesh_oneiros_consolidation`
audit record — there is no field on a node in which to record what it absorbed.

`--dry-run` needs no network and changes nothing. It is the useful report on its
own: how fragmented the substrate's identity is, and which nodes are claiming
the same name.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from theogony.agents.factory import build_llm_from_settings
from theogony.config.settings import Settings
from theogony.mesh.runtime.consolidation import (
    DEFAULT_MAX_NAME_DF,
    Adjudicator,
    Describer,
    LLMAdjudicator,
    LLMDescriber,
    ReplayAdjudicator,
    description_head,
    run_consolidation,
)
from theogony.mesh.runtime.oneiros_tick import MeshRuntime
from theogony.mesh.seeds.wikidata5m.embedder import BGESmallEnEmbedder


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="data/mesh-founding", type=Path)
    ap.add_argument("--dry-run", action="store_true", help="propose only; no network, no writes")
    ap.add_argument("--max-name-df", type=int, default=DEFAULT_MAX_NAME_DF)
    ap.add_argument("--coalesce", choices=("sum", "max"), default="sum")
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument(
        "--no-describe",
        action="store_true",
        help="merge without regenerating descriptions (isolates the merge from the rewrite)",
    )
    ap.add_argument("--out", type=Path, help="write proposals and verdicts as JSON here")
    ap.add_argument(
        "--verdicts",
        type=Path,
        help="replay the identity decisions from an earlier --out file instead of asking again",
    )
    args = ap.parse_args()

    settings = Settings()
    runtime = MeshRuntime.open(args.root)

    adjudicator: Adjudicator | None = None
    describer: Describer | None = None
    embed = None
    if not args.dry_run:
        if args.verdicts:
            adjudicator = ReplayAdjudicator.from_export(
                json.loads(args.verdicts.read_text(encoding="utf-8"))
            )
        else:
            adjudicator = LLMAdjudicator(
                build_llm_from_settings(settings), concurrency=args.concurrency
            )
        print(f"adjudicator: {adjudicator.model_id}")
        if not args.no_describe:
            llm = build_llm_from_settings(settings)
            describer = LLMDescriber(llm, concurrency=args.concurrency)
            embed = BGESmallEnEmbedder().embed_many
            print(f"describer:   {llm.model_id}")

    result, proposals, verdicts = asyncio.run(
        run_consolidation(
            runtime,
            adjudicator=adjudicator,
            describer=describer,
            embed=embed,
            max_name_df=args.max_name_df,
            coalesce=args.coalesce,
        )
    )

    print(f"\nTicks auf diesem Mesh: {runtime.tick_count()}")
    print(f"proposals            {result.proposals}")
    if result.dry_run:
        by_anchor: dict[str, list[str]] = {}
        nodes = {str(n.id): n for n in runtime.nodes.iter_consolidated(page_size=1024)}
        for proposal in proposals:
            by_anchor.setdefault(proposal.anchor_id, []).append(proposal.member_id)
        print(f"anchors              {len(by_anchor)}")
        print(f"members              {len({p.member_id for p in proposals})}")
        for anchor_id, members in sorted(by_anchor.items(), key=lambda kv: -len(kv[1]))[:10]:
            print(f"\n  {description_head(nodes[anchor_id])!r} <- {len(members)}")
            for member_id in members[:8]:
                print(f"      {description_head(nodes[member_id])!r}")
    else:
        print(f"verdicts             {result.verdict_counts}")
        print(f"clusters merged      {result.clusters_merged}")
        print(f"nodes absorbed       {result.nodes_absorbed}")
        print(f"ambiguous, dropped   {result.ambiguous_dropped}")
        print(f"nodes  {result.nodes_before} -> {result.nodes_after}")
        print(f"edges  {result.edges_before} -> {result.edges_after}")
        print(f"  self-edges dropped {result.self_edges_dropped}")
        print(f"  coalesced          {result.edges_coalesced}")
        print(f"descriptions         {result.descriptions_regenerated}")
        print(f"  name refused       {result.description_fallbacks}")
        print(f"audit                {result.audit_id}")

    if args.out:
        args.out.write_text(
            json.dumps(
                {
                    "result": result.as_detail(),
                    "proposals": [vars(p) for p in proposals],
                    "verdicts": [
                        {"decision": v.decision, "reason": v.reason, **vars(v.proposal)}
                        for v in verdicts
                    ],
                },
                indent=2,
                default=str,
            ),
            encoding="utf-8",
        )
        print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
