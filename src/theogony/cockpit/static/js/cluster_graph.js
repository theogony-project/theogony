function mountClusterGraph() {
  const el = document.getElementById("cluster-graph");
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
  for (const e of data.intra || []) {
    elements.push({
      data: { id: e.id || `${e.source}-${e.target}`, source: e.source, target: e.target, w: e.weight },
      classes: "intra",
    });
  }
  for (const e of data.cross || []) {
    elements.push({
      data: { id: e.id || `x-${e.source}-${e.target}`, source: e.source, target: e.target, w: e.weight },
      classes: "cross",
    });
  }
  cytoscape({
    container: el,
    elements,
    style: [
      { selector: "node", style: { label: "data(label)", "font-size": "10px", color: "#e2e8f0", "background-color": "#334155" } },
      { selector: "edge.intra", style: { width: 2, "line-color": "#cbd5e1", "target-arrow-color": "#cbd5e1", "curve-style": "bezier" } },
      { selector: "edge.cross", style: { width: 2, "line-color": "#f87171", "target-arrow-color": "#f87171", "curve-style": "bezier" } },
    ],
    layout: { name: "cose", animate: false },
  });
}
window.__cockpitMountCluster = mountClusterGraph;
document.addEventListener("DOMContentLoaded", mountClusterGraph);
