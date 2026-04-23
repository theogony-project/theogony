function mountHoverLupe() {
  const el = document.getElementById("hover-lupe");
  if (!el || typeof cytoscape === "undefined") return;
  const raw = el.getAttribute("data-graph");
  if (!raw) return;
  let data;
  try { data = JSON.parse(raw); } catch (_) { return; }
  el.innerHTML = "";
  const elements = [];
  for (const n of data.nodes || []) {
    elements.push({ data: { id: n.id, label: n.label || n.id } });
  }
  for (const e of data.edges || []) {
    elements.push({
      data: { id: e.id || `${e.source}-${e.target}`, source: e.source, target: e.target, w: e.weight },
    });
  }
  cytoscape({
    container: el,
    elements,
    style: [
      { selector: "node", style: { label: "data(label)", "font-size": "10px", color: "#e2e8f0", "background-color": "#475569" } },
      { selector: "edge", style: { width: "mapData(w, 0, 1, 1, 4)", "line-color": "#94a3b8", "target-arrow-color": "#94a3b8", "curve-style": "bezier" } },
    ],
    layout: { name: "cose", animate: false },
  });
}
window.__cockpitMountHoverLupe = mountHoverLupe;
document.addEventListener("DOMContentLoaded", mountHoverLupe);
