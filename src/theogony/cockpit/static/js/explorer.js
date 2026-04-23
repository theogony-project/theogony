/* Pantheon Explorer — streamed phases + d3 force-graph + chronicle append. */

(function () {
  const root = document.getElementById("explorer-root");
  const form = document.getElementById("explorer-form");
  const qEl = document.getElementById("explorer-q");
  const kEl = document.getElementById("explorer-k");
  const hopsEl = document.getElementById("explorer-hops");
  const statusEl = document.getElementById("explorer-status");
  const answerEl = document.getElementById("explorer-answer");
  const vectorEl = document.getElementById("explorer-vector");
  const timingEl = document.getElementById("explorer-timing");
  const saveBtn = document.getElementById("explorer-save");
  const phases = {
    embed: document.getElementById("phase-embed"),
    retrieve: document.getElementById("phase-retrieve"),
    synth: document.getElementById("phase-synth"),
  };
  const svg = d3.select("#explorer-graph");
  if (!form || !svg.node()) return;

  const sampleOnly = root && root.dataset.sampleOnly === "true";
  const appendEnabled = root && root.dataset.appendEnabled === "true";

  const TYPE_COLOR = {
    person: "#f472b6",
    place: "#34d399",
    concept: "#60a5fa",
    event: "#fbbf24",
    claim: "#a78bfa",
    work: "#22d3ee",
    organization: "#f97316",
    time: "#94a3b8",
    quantity: "#94a3b8",
    source: "#94a3b8",
    other: "#94a3b8",
  };

  let simulation = null;
  /** @type {object | null} */
  let lastPayload = null;

  if (saveBtn) {
    if (sampleOnly || !appendEnabled) {
      saveBtn.disabled = true;
      saveBtn.title = sampleOnly
        ? "Disabled in sample-only cockpit mode"
        : "Disabled (THEOGONY_MCP_APPEND__ENABLED=false)";
      saveBtn.classList.add("opacity-40", "cursor-not-allowed");
    }
  }

  function clearGraph() {
    svg.selectAll("*").remove();
  }

  function setPhase(name, on) {
    const el = phases[name];
    if (!el) return;
    el.classList.toggle("explorer-phase-on", !!on);
  }

  function resetPhases() {
    setPhase("embed", false);
    setPhase("retrieve", false);
    setPhase("synth", false);
  }

  function setStatus(text, level) {
    statusEl.textContent = text || "";
    statusEl.className =
      "text-xs min-h-[1rem] " +
      (level === "error"
        ? "text-rose-400"
        : level === "ok"
        ? "text-emerald-400"
        : "text-slate-500");
  }

  function renderVector(vec) {
    vectorEl.innerHTML = "";
    if (!vec || !vec.length) {
      vectorEl.textContent = "(no embedding preview)";
      return;
    }
    const w = 280;
    const h = 32;
    const max = Math.max(0.01, ...vec.map((v) => Math.abs(v)));
    const svgV = d3
      .select(vectorEl)
      .append("svg")
      .attr("viewBox", `0 0 ${w} ${h}`)
      .attr("class", "w-full h-8");
    const bw = w / vec.length;
    svgV
      .selectAll("rect")
      .data(vec)
      .join("rect")
      .attr("x", (_, i) => i * bw)
      .attr("y", (d) => (d >= 0 ? h / 2 - (Math.abs(d) / max) * (h / 2) : h / 2))
      .attr("width", bw - 0.5)
      .attr("height", (d) => (Math.abs(d) / max) * (h / 2))
      .attr("fill", (d) => (d >= 0 ? "#fbbf24" : "#60a5fa"));
    const label = document.createElement("div");
    label.className = "text-[10px] text-slate-500 mt-1";
    label.textContent = `first ${vec.length} components of the query embedding`;
    vectorEl.appendChild(label);
  }

  function renderTiming(t, retrieval) {
    if (!t) {
      timingEl.textContent = "";
      return;
    }
    const total = Math.max(1, t.total_ms || 0);
    const parts = [
      ["embed", t.embed_ms],
      ["retrieve", t.multi_hop_ms],
      ["synth", t.synthesis_ms],
    ];
    timingEl.innerHTML = `
      <div class="flex gap-1 h-2 rounded overflow-hidden bg-slate-800">
        ${parts
          .map(
            (p, i) =>
              `<div title="${p[0]}: ${p[1]}ms"
                class="${["bg-sky-500", "bg-emerald-500", "bg-amber-500"][i]}"
                style="width:${Math.max(2, ((p[1] || 0) / total) * 100)}%"></div>`
          )
          .join("")}
      </div>
      <div class="text-[10px] text-slate-500 mt-1">
        ${t.embed_ms}ms embed · ${t.multi_hop_ms}ms retrieve ·
        ${t.synthesis_ms}ms synth · total ${t.total_ms}ms ·
        ${retrieval.seed_count} seeds → ${retrieval.final_node_count} nodes
        (k=${retrieval.k}, hops=${retrieval.hops}, ${retrieval.strategy})
      </div>`;
  }

  function edgeEndpointIds(d) {
    const s = typeof d.source === "object" && d.source ? d.source.id : d.source;
    const t = typeof d.target === "object" && d.target ? d.target.id : d.target;
    return [String(s), String(t)];
  }

  function renderGraph(payload) {
    clearGraph();
    const width = svg.node().clientWidth;
    const height = svg.node().clientHeight;
    if (!width || !height) return;

    const cited = new Set(payload.answer.cited_node_ids || []);
    const nodeData = (payload.constellation.nodes || []).map((n) => ({
      ...n,
      r: 6 + (n.confidence || 0.4) * 10,
      color: cited.has(n.id) ? "#34d399" : TYPE_COLOR[n.node_type] || "#94a3b8",
    }));
    const queryNode = {
      id: "__query__",
      label: payload.query,
      isQuery: true,
      r: 14,
      color: "#fbbf24",
      x: width / 2,
      y: height / 2,
      fx: width / 2,
      fy: height / 2,
    };
    const nodes = [queryNode, ...nodeData];

    const realEdges = (payload.constellation.edges || []).map((e) => ({
      ...e,
      kind: "real",
    }));
    // Link every node in the constellation to the query (up to a cap) so
    // nothing "floats" when retrieval.final_node_count > old hard cap of 8.
    const spokeCap = Math.min(nodeData.length, 32);
    const seedTop = nodeData
      .slice()
      .sort((a, b) => (b.confidence || 0) - (a.confidence || 0))
      .slice(0, spokeCap);
    const seedEdges = seedTop.map((n) => ({
      source: "__query__",
      target: n.id,
      weight: n.confidence,
      kind: "seed",
    }));
    const links = [...seedEdges, ...realEdges];

    const pulses = svg
      .append("g")
      .selectAll("circle")
      .data([0, 1, 2])
      .join("circle")
      .attr("cx", width / 2)
      .attr("cy", height / 2)
      .attr("r", 12)
      .attr("fill", "none")
      .attr("stroke", "#fbbf24")
      .attr("stroke-opacity", 0.45)
      .attr("stroke-width", 1.2);
    pulses
      .transition()
      .delay((_, i) => i * 220)
      .duration(2000)
      .ease(d3.easeCubicOut)
      .attr("r", Math.min(width, height) * 0.42)
      .attr("stroke-opacity", 0)
      .remove();

    const linkSel = svg
      .append("g")
      .attr("stroke-linecap", "round")
      .selectAll("line")
      .data(links)
      .join("line")
      .attr("stroke", (d) => {
        if (d.kind === "seed") return "#fbbf24";
        const [s, t] = edgeEndpointIds(d);
        return cited.has(s) && cited.has(t) ? "#34d399" : "#475569";
      })
      .attr("stroke-opacity", (d) => (d.kind === "seed" ? 0.55 : 0.65))
      .attr("stroke-width", (d) => 1 + (d.weight || 0.3) * 3)
      .attr("stroke-dasharray", (d) => (d.kind === "seed" ? "3 4" : null));

    const nodeSel = svg
      .append("g")
      .selectAll("g")
      .data(nodes, (d) => d.id)
      .join("g")
      .attr("class", "explorer-node")
      .style("cursor", (d) => (d.isQuery ? "default" : "pointer"))
      .on("click", (_, d) => {
        if (!d.isQuery) {
          window.open(`/cockpit/browser/node/${encodeURIComponent(d.id)}`, "_blank");
        }
      });

    nodeSel
      .append("circle")
      .attr("r", 0)
      .attr("fill", (d) => d.color)
      .attr("opacity", (d) => (d.isQuery ? 0.95 : 1))
      .attr("stroke", (d) => (d.is_cited ? "#facc15" : "#0f172a"))
      .attr("stroke-width", (d) => (d.is_cited ? 2.2 : 1))
      .transition()
      .duration(650)
      .ease(d3.easeBackOut.overshoot(1.2))
      .attr("r", (d) => d.r);

    nodeSel
      .append("title")
      .text(
        (d) =>
          d.isQuery
            ? `query: ${d.label}`
            : `${d.label} [${d.node_type}] conf=${(d.confidence || 0).toFixed(2)}`
      );

    nodeSel
      .filter((d) => d.is_cited || d.isQuery)
      .append("text")
      .text((d) => (d.label.length > 28 ? d.label.slice(0, 27) + "…" : d.label))
      .attr("dy", (d) => -d.r - 4)
      .attr("text-anchor", "middle")
      .attr("font-size", 10)
      .attr("fill", "#e2e8f0")
      .attr("pointer-events", "none");

    if (simulation) simulation.stop();
    simulation = d3
      .forceSimulation(nodes)
      .force(
        "link",
        d3
          .forceLink(links)
          .id((d) => d.id)
          .distance((l) => (l.kind === "seed" ? 88 : 58))
          .strength((l) => (l.kind === "seed" ? 0.18 : 0.42))
      )
      .force("charge", d3.forceManyBody().strength(-200))
      .force("center", d3.forceCenter(width / 2, height / 2))
      .force("collide", d3.forceCollide().radius((d) => d.r + 5))
      .alpha(1)
      .alphaDecay(0.045);

    simulation.on("tick", () => {
      linkSel
        .attr("x1", (d) => d.source.x)
        .attr("y1", (d) => d.source.y)
        .attr("x2", (d) => d.target.x)
        .attr("y2", (d) => d.target.y);
      nodeSel.attr("transform", (d) => `translate(${d.x},${d.y})`);
    });
  }

  function escapeHtml(s) {
    return s
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  function applyPayload(payload) {
    lastPayload = payload;
    const nNodes = (payload.constellation.nodes || []).length;
    const nConstEdges = (payload.constellation.edges || []).length;
    const nSpokes = Math.min(nNodes, 32);
    setStatus(
      `verdict=${payload.verdict} · ${nNodes} nodes · ${nConstEdges} graph edges · ${nSpokes} query links`,
      "ok"
    );
    const gaps =
      payload.constellation.gaps && payload.constellation.gaps.length
        ? `<div class="text-amber-300/90 text-xs mb-2">gaps: ${payload.constellation.gaps.join(", ")}</div>`
        : "";
    answerEl.innerHTML =
      gaps +
      `<div>${payload.answer.text ? escapeHtml(payload.answer.text) : "<span class='text-slate-500 italic'>(no prose; offline / stub synthesizer)</span>"}</div>`;
    renderVector(payload.query_embedding_preview);
    renderTiming(payload.timing_ms, payload.retrieval);
    renderGraph(payload);
  }

  async function parseSseStream(resp) {
    const reader = resp.body.getReader();
    const dec = new TextDecoder();
    let buf = "";
    let finalPayload = null;
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      let sep;
      while ((sep = buf.indexOf("\n\n")) >= 0) {
        const block = buf.slice(0, sep);
        buf = buf.slice(sep + 2);
        for (const line of block.split("\n")) {
          if (!line.startsWith("data: ")) continue;
          const obj = JSON.parse(line.slice(6));
          if (obj.type === "error") {
            throw new Error(obj.message || "error");
          }
          if (obj.type === "phase") {
            resetPhases();
            if (obj.phase === "embed") setPhase("embed", true);
            if (obj.phase === "retrieve") setPhase("retrieve", true);
            if (obj.phase === "synthesize") setPhase("synth", true);
          }
          if (obj.type === "complete") {
            finalPayload = obj.payload;
            resetPhases();
          }
        }
      }
    }
    return finalPayload;
  }

  async function ask(ev) {
    ev.preventDefault();
    const q = (qEl.value || "").trim();
    if (!q) return;
    resetPhases();
    setStatus("connecting…");
    answerEl.innerHTML = `<span class="text-slate-500">Listening to the Chronik…</span>`;
    clearGraph();
    lastPayload = null;
    let resp;
    try {
      resp = await fetch("/cockpit/api/ask-stream", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
        body: JSON.stringify({
          q,
          k: parseInt(kEl.value, 10) || 10,
          hops: parseInt(hopsEl.value, 10) || 2,
        }),
      });
    } catch (err) {
      setStatus("network error: " + err, "error");
      return;
    }
    if (!resp.ok) {
      setStatus("HTTP " + resp.status, "error");
      try {
        answerEl.textContent = await resp.text();
      } catch (_) {
        /* ignore */
      }
      return;
    }
    let payload;
    try {
      payload = await parseSseStream(resp);
    } catch (e) {
      setStatus(String(e.message || e), "error");
      answerEl.textContent = String(e.message || e);
      resetPhases();
      return;
    }
    if (!payload) {
      setStatus("empty stream", "error");
      return;
    }
    if (payload.error) {
      setStatus(payload.error, "error");
      answerEl.textContent = payload.error;
      resetPhases();
      return;
    }
    applyPayload(payload);
  }

  async function saveHypothesis() {
    if (!lastPayload || sampleOnly || !appendEnabled) return;
    const q = lastPayload.query || "";
    const ans = (lastPayload.answer && lastPayload.answer.text) || "";
    const body =
      (ans.trim() ? ans : "") +
      (ans.trim() && q ? "\n\n—\n\n" : "") +
      (q ? `Question:\n${q}` : "");
    const title = (q.length > 80 ? q.slice(0, 77) + "…" : q) || "Explorer hypothesis";
    setStatus("writing to Chronik…");
    let resp;
    try {
      resp = await fetch("/cockpit/api/chronicle-append", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          fragments: [{ title: title, body: body || q }],
          context_note: `run_id=${lastPayload.run_id} verdict=${lastPayload.verdict}`,
        }),
      });
    } catch (err) {
      setStatus("network error: " + err, "error");
      return;
    }
    const out = await resp.json();
    const detailMsg =
      typeof out.detail === "string"
        ? out.detail
        : Array.isArray(out.detail)
          ? out.detail.map((x) => (x && x.msg) || JSON.stringify(x)).join("; ")
          : null;
    if (!resp.ok || out.error) {
      setStatus(out.error || detailMsg || "append failed", "error");
      return;
    }
    setStatus(`saved ${out.fragment_count} node(s): ${(out.upserted_node_ids || []).join(", ")}`, "ok");
  }

  form.addEventListener("submit", ask);
  if (saveBtn) saveBtn.addEventListener("click", saveHypothesis);
})();
