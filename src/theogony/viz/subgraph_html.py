"""
Write a self-contained HTML file that renders nodes and edges with Cytoscape.js.

No extra Python packages: the page loads Cytoscape from the same pinned URL
as the cockpit cluster / browser panels. Use after ``TopologyParser.parse_chunk``,
Neo4j exports, or any list of :class:`~theogony.core.model.KnowledgeNode` /
:class:`~theogony.core.model.KnowledgeEdge`.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from theogony.core.model import KnowledgeEdge, KnowledgeNode

_CYTO_UNPKG = "https://unpkg.com/cytoscape@3.28.1/dist/cytoscape.min.js"


def _node_id(n: KnowledgeNode | Mapping[str, Any]) -> str:
    if isinstance(n, KnowledgeNode):
        return n.id
    return str(n["id"])


def _node_label(n: KnowledgeNode | Mapping[str, Any]) -> str:
    if isinstance(n, KnowledgeNode):
        return n.label
    return str(n.get("label") or n.get("id") or "")


def _edge_endpoints(
    e: KnowledgeEdge | Mapping[str, Any],
) -> tuple[str, str, str | None, float]:
    if isinstance(e, KnowledgeEdge):
        return e.source_id, e.target_id, e.id or None, float(e.weight)
    sid = str(e["source_id"])
    tid = str(e["target_id"])
    eid = e.get("id")
    wid = float(e.get("weight", 0.5))
    return sid, tid, str(eid) if eid else None, wid


def _edge_relation(e: KnowledgeEdge | Mapping[str, Any]) -> str:
    if isinstance(e, KnowledgeEdge):
        return e.relation_type
    return str(e.get("relation_type", ""))


def chronik_subgraph_payload(
    nodes: Sequence[KnowledgeNode | Mapping[str, Any]],
    edges: Sequence[KnowledgeEdge | Mapping[str, Any]],
) -> dict[str, Any]:
    """
    Build a JSON-serialisable graph dict for Cytoscape ``elements``.

    Expected keys per node: ``id``, ``label``. Per edge: ``source_id``,
    ``target_id``, optional ``id``, ``weight``, ``relation_type``.
    """
    node_rows: list[dict[str, Any]] = []
    for n in nodes:
        nid = _node_id(n)
        node_rows.append({"id": nid, "label": _node_label(n)})
    edge_rows: list[dict[str, Any]] = []
    for e in edges:
        sid, tid, eid, w = _edge_endpoints(e)
        rel = _edge_relation(e)
        edge_rows.append(
            {
                "id": eid or f"EDGE-{sid}->{tid}",
                "source": sid,
                "target": tid,
                "weight": w,
                "relation_type": rel,
            }
        )
    return {"nodes": node_rows, "edges": edge_rows}


def write_chronik_subgraph_html(
    path: str | Path,
    *,
    nodes: Sequence[KnowledgeNode | Mapping[str, Any]],
    edges: Sequence[KnowledgeEdge | Mapping[str, Any]],
    title: str = "Chronik subgraph",
) -> None:
    """
    Write ``path`` (e.g. ``mesh.html``); open in a browser to pan/zoom the graph.

    Edges whose endpoints are missing from ``nodes`` are still emitted; Cytoscape
    may omit or warn — pass a closed subgraph for best layout.
    """
    payload = chronik_subgraph_payload(nodes, edges)
    raw = json.dumps(payload, ensure_ascii=False)
    # JSON must not break the HTML script assignment.
    safe = raw.replace("</", "<\\/")
    nn, ne = len(payload["nodes"]), len(payload["edges"])
    head_line = f"{_html_escape(title)} — {nn} nodes, {ne} edges"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>{_html_escape(title)}</title>
  <style>
    html, body {{ margin: 0; height: 100%; background: #020617; color: #e2e8f0;
      font-family: system-ui, sans-serif; }}
    #head {{ padding: 10px 14px; border-bottom: 1px solid #334155; font-size: 14px; }}
    #cy {{ height: calc(100% - 48px); width: 100%; }}
  </style>
</head>
<body>
  <div id="head">{head_line}</div>
  <div id="cy"></div>
  <script src="{_CYTO_UNPKG}" crossorigin="anonymous"></script>
  <script>
    const data = {safe};
    const elements = [];
    for (const n of data.nodes || []) {{
      elements.push({{ data: {{ id: n.id, label: n.label || n.id }} }});
    }}
    for (const e of data.edges || []) {{
      elements.push({{
        data: {{
          id: e.id,
          source: e.source,
          target: e.target,
          w: e.weight,
          rel: e.relation_type || "",
        }},
      }});
    }}
    cytoscape({{
      container: document.getElementById("cy"),
      elements,
      style: [
        {{ selector: "node", style: {{
          label: "data(label)",
          "font-size": "11px",
          color: "#e2e8f0",
          "background-color": "#475569",
          "text-valign": "center",
          "text-halign": "center",
        }} }},
        {{ selector: "edge", style: {{
          width: "mapData(w, 0, 1, 1, 4)",
          "line-color": "#94a3b8",
          "target-arrow-color": "#94a3b8",
          "curve-style": "bezier",
          "target-arrow-shape": "triangle",
          label: "data(rel)",
          "font-size": "9px",
          color: "#94a3b8",
        }} }},
      ],
      layout: {{ name: "cose", animate: true, randomize: true }},
      wheelSensitivity: 0.35,
    }});
  </script>
</body>
</html>
"""
    Path(path).write_text(html, encoding="utf-8")


def _html_escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
