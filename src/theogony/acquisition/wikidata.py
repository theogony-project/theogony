"""WikidataAdapter — thin acquisition wrapper over WikidataClient (W11)."""

from __future__ import annotations

import re
from typing import Any

from theogony.acquisition.base import RawContent, SourceCandidate
from theogony.extraction.wikidata_client import WikidataClient

_QID_RE = re.compile(r"^Q\d+$")


class WikidataAdapter:
    """Discover and acquire synthetic Wikidata text blobs for ingest."""

    def __init__(self, *, client: WikidataClient) -> None:
        self._client = client

    @property
    def source_type(self) -> str:
        return "wikidata"

    def supports(self, source_type: str) -> bool:
        return source_type == "wikidata"

    async def search(self, query: str, *, limit: int = 5) -> list[SourceCandidate]:
        q = query.strip()
        if not q:
            return []
        if _QID_RE.match(q):
            rows = await self._client.fetch_labels_aliases([q], languages=["en", "de"])
            per = rows.get(q, {})
            label = ""
            for lang in ("en", "de"):
                names = per.get(lang, [])
                if names:
                    label = names[0]
                    break
            title = label or q
            url = f"https://www.wikidata.org/wiki/{q}"
            return [
                SourceCandidate(
                    source_type="wikidata",
                    identifier=q,
                    title=title,
                    authors=[],
                    languages=["en"],
                    url=url,
                    download_url=url,
                    metadata={
                        "wikidata_qid": q,
                        "wikidata_description": "",
                        "estimated_bytes": 4096,
                        "copyright": False,
                    },
                )
            ]
        hits = await self._client.search(q, language="en", limit=limit)
        out: list[SourceCandidate] = []
        for h in hits:
            url = f"https://www.wikidata.org/wiki/{h.qid}"
            desc = (h.description or "").strip()
            out.append(
                SourceCandidate(
                    source_type="wikidata",
                    identifier=h.qid,
                    title=h.label or h.qid,
                    authors=[],
                    languages=[h.language],
                    url=url,
                    download_url=url,
                    metadata={
                        "wikidata_qid": h.qid,
                        "wikidata_description": desc,
                        "estimated_bytes": 4096,
                        "copyright": False,
                    },
                )
            )
        return out

    async def acquire(self, candidate: SourceCandidate) -> RawContent:
        qid = candidate.identifier
        rows = await self._client.fetch_labels_aliases([qid], languages=["en", "de"])
        per_lang = rows.get(qid, {})
        lines: list[str] = [f"Wikidata entity {qid}", f"Title: {candidate.title}"]
        for lang, names in sorted(per_lang.items()):
            if names:
                lines.append(f"[{lang}] " + " | ".join(names))
        body = "\n".join(lines) + "\n"
        meta: dict[str, Any] = dict(candidate.metadata)
        meta["wikidata_qid"] = qid
        meta.setdefault("copyright", False)
        return RawContent(
            source_type="wikidata",
            identifier=qid,
            title=candidate.title,
            authors=[],
            language=candidate.languages[0] if candidate.languages else None,
            content=body,
            content_format="text/plain; charset=utf-8",
            url=candidate.url,
            bytes_acquired=len(body.encode("utf-8")),
            metadata=meta,
        )

    async def aclose(self) -> None:
        return None


__all__ = ["WikidataAdapter"]
