"""
Harvest deterministic Wikipedia out-links + Wikidata Q-IDs (+ P31 hints).

Runs alongside LLM topology extraction: hub node for the article, stub nodes for
linked titles, ``WIKILINK`` edges, ``external_ids['wikidata']`` when resolvable,
and ``properties['wikidata_P31']`` from ``wbgetentities`` (no separate type nodes yet).
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from theogony.core.model import (
    EdgeType,
    KnowledgeEdge,
    KnowledgeNode,
    Layer,
    NodeType,
    SourceRef,
)
from theogony.extraction.wikipedia_full import WIKI_USER_AGENT

_ENWIKI_API = "https://en.wikipedia.org/w/api.php"
_WD_API = "https://www.wikidata.org/w/api.php"


def _slug(title: str) -> str:
    return title.replace(" ", "_")


async def _wiki_get_json(
    client: httpx.AsyncClient,
    params: dict[str, Any],
    *,
    timeout_s: float = 60.0,
) -> dict[str, Any]:
    headers = {"User-Agent": WIKI_USER_AGENT}
    r = await client.get(_ENWIKI_API, params=params, headers=headers, timeout=timeout_s)
    r.raise_for_status()
    payload: dict[str, Any] = r.json()
    return payload


async def fetch_outgoing_mainspace_links(
    client: httpx.AsyncClient,
    title: str,
    *,
    max_links: int,
) -> list[str]:
    """Outgoing article-namespace links from ``title`` (paginated)."""
    seen: set[str] = set()
    out: list[str] = []
    params: dict[str, Any] = {
        "action": "query",
        "format": "json",
        "titles": title,
        "prop": "links",
        "plnamespace": "0",
        "pllimit": "500",
    }
    while len(out) < max_links:
        data = await _wiki_get_json(client, params)
        pages = (data.get("query") or {}).get("pages") or {}
        for page in pages.values():
            if not isinstance(page, dict):
                continue
            for link in page.get("links") or []:
                t = link.get("title")
                if not t or t in seen:
                    continue
                seen.add(t)
                out.append(t)
                if len(out) >= max_links:
                    return out
        cont = data.get("continue")
        if not cont or "plcontinue" not in cont:
            break
        params["plcontinue"] = cont["plcontinue"]
        await asyncio.sleep(0.15)
    return out


async def fetch_wikidata_qids_for_titles(
    client: httpx.AsyncClient,
    titles: list[str],
) -> dict[str, str | None]:
    """Map canonical Wikipedia title → Wikidata Q-ID (or None). Batches of 40."""
    result: dict[str, str | None] = {}
    batch_size = 40
    for i in range(0, len(titles), batch_size):
        batch = titles[i : i + batch_size]
        params = {
            "action": "query",
            "format": "json",
            "titles": "|".join(batch),
            "prop": "pageprops",
            "ppprop": "wikibase_item",
        }
        data = await _wiki_get_json(client, params)
        for page in (data.get("query") or {}).get("pages", {}).values():
            if not isinstance(page, dict):
                continue
            t = page.get("title")
            if not t:
                continue
            props = page.get("pageprops") or {}
            qid = props.get("wikibase_item")
            if isinstance(qid, str) and qid.startswith("Q") and qid[1:].isdigit():
                result[t] = qid
            else:
                result[t] = None
        await asyncio.sleep(0.12)
    return result


async def fetch_p31_for_qids(client: httpx.AsyncClient, qids: list[str]) -> dict[str, list[str]]:
    """Return mapping Q-id → list of P31 target Q-ids (instance-of)."""
    out: dict[str, list[str]] = {}
    batch_size = 45
    headers = {"User-Agent": WIKI_USER_AGENT}
    for i in range(0, len(qids), batch_size):
        batch = qids[i : i + batch_size]
        ids_param = "|".join(batch)
        params = {
            "action": "wbgetentities",
            "format": "json",
            "ids": ids_param,
            "props": "claims",
        }
        r = await client.get(_WD_API, params=params, headers=headers, timeout=60.0)
        r.raise_for_status()
        data = r.json()
        entities = data.get("entities") or {}
        for qid, ent in entities.items():
            if not isinstance(ent, dict):
                continue
            claims = ent.get("claims") or {}
            p31 = claims.get("P31") or []
            targets: list[str] = []
            for stmt in p31:
                try:
                    dv = (stmt.get("mainsnak") or {}).get("datavalue") or {}
                    val = dv.get("value")
                    if isinstance(val, dict):
                        tid = val.get("id")
                        if isinstance(tid, str) and tid.startswith("Q"):
                            targets.append(tid)
                except (TypeError, KeyError, AttributeError):
                    continue
            if targets:
                out[qid] = targets
        await asyncio.sleep(0.2)
    return out


async def harvest_wikipedia_links_mesh(
    client: httpx.AsyncClient,
    *,
    article_title: str,
    extractor_run_id: str,
    max_links: int = 1500,
) -> tuple[list[KnowledgeNode], list[KnowledgeEdge]]:
    """
    Build hub + link-target stubs + WIKILINK edges; enrich with Wikidata Q + P31 hints.

    Does not embed vectors — caller runs ``SentenceTransformer`` like topology nodes.
    """
    slug = _slug(article_title)
    hub_ref = SourceRef(
        source_type="wikipedia",
        identifier=slug,
        location="article_hub",
    )
    hub = KnowledgeNode(
        label=article_title,
        node_type=NodeType.CONCEPT,
        layer=Layer.EPHEMERA,
        source_ref=hub_ref,
        properties={
            "harvest_role": "wikipedia_article_hub",
            "extractor_run_id": extractor_run_id,
        },
    )

    links = await fetch_outgoing_mainspace_links(client, article_title, max_links=max_links)
    nodes: list[KnowledgeNode] = [hub]
    edges: list[KnowledgeEdge] = []

    titles_for_props = [article_title] + links
    qmap = await fetch_wikidata_qids_for_titles(client, titles_for_props)
    hub_q = qmap.get(article_title)
    if hub_q:
        hub.external_ids["wikidata"] = hub_q

    unique_qs = list(dict.fromkeys(q for q in qmap.values() if q))
    p31_map = await fetch_p31_for_qids(client, unique_qs) if unique_qs else {}

    if hub_q and hub_q in p31_map:
        hub.properties["wikidata_P31"] = p31_map[hub_q]

    for target_title in links:
        tslug = _slug(target_title)
        stub_ref = SourceRef(
            source_type="wikipedia",
            identifier=tslug,
            location=f"link_target:{slug}",
        )
        stub = KnowledgeNode(
            label=target_title,
            node_type=NodeType.CONCEPT,
            layer=Layer.EPHEMERA,
            source_ref=stub_ref,
            properties={
                "harvest_role": "wikipedia_link_target",
                "extractor_run_id": extractor_run_id,
                "linked_from_article": slug,
            },
        )
        tq = qmap.get(target_title)
        if tq:
            stub.external_ids["wikidata"] = tq
            if tq in p31_map:
                stub.properties["wikidata_P31"] = p31_map[tq]
        nodes.append(stub)

        edges.append(
            KnowledgeEdge(
                source_id=hub.id,
                target_id=stub.id,
                relation_type="WIKILINK",
                epistemic_type=EdgeType.EXTRACTION,
                weight=0.95,
                confidence=0.95,
                source_ref=hub_ref,
                evidence_span=None,
                properties={
                    "channel": "wikipedia_api_links",
                    "extractor_run_id": extractor_run_id,
                },
            )
        )

    return nodes, edges


__all__ = [
    "fetch_outgoing_mainspace_links",
    "fetch_p31_for_qids",
    "fetch_wikidata_qids_for_titles",
    "harvest_wikipedia_links_mesh",
]
