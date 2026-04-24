/* Growth live panel + POST /cockpit/api/growth-stream (W8). Loaded only when ?growth=on. */

(function () {
  const root = document.getElementById("explorer-root");
  const form = document.getElementById("explorer-form");
  if (!root || root.dataset.growth !== "on" || !form) return;

  const logEl = document.getElementById("explorer-growth-log");
  const qEl = document.getElementById("explorer-q");
  const kEl = document.getElementById("explorer-k");
  const hopsEl = document.getElementById("explorer-hops");
  const thinkingMaxEl = document.getElementById("explorer-thinking-max");
  const statusEl = document.getElementById("explorer-status");
  const vectorEl = document.getElementById("explorer-vector");
  const timingEl = document.getElementById("explorer-timing");
  const svg = d3.select("#explorer-graph");
  const phases = {
    chat: document.getElementById("phase-chat"),
    embed: document.getElementById("phase-embed"),
    retrieve: document.getElementById("phase-retrieve"),
    synth: document.getElementById("phase-synth"),
  };

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

  function appendGrowthLine(text) {
    if (!logEl) return;
    const row = document.createElement("div");
    row.className = "text-[11px] font-mono text-slate-300 border-b border-slate-800/80 py-0.5";
    row.textContent = text;
    logEl.appendChild(row);
    logEl.scrollTop = logEl.scrollHeight;
  }

  function setPhase(name, on) {
    const el = phases[name];
    if (!el) return;
    el.classList.toggle("explorer-phase-on", !!on);
  }

  function resetPhases() {
    setPhase("chat", false);
    setPhase("embed", false);
    setPhase("retrieve", false);
    setPhase("synth", false);
  }

  function setStatus(text, level) {
    if (!statusEl) return;
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
    if (!vectorEl) return;
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
    if (!timingEl || !t) {
      if (timingEl) timingEl.textContent = "";
      return;
    }
    const chatMs = t.chat_prep_ms != null ? t.chat_prep_ms : 0;
    const parts = [
      ["chat", chatMs],
      ["embed", t.embed_ms],
      ["retrieve", t.multi_hop_ms],
      ["synth", t.synthesis_ms],
    ];
    const barTotal = Math.max(1, parts.reduce((a, p) => a + (p[1] || 0), 0));
    timingEl.innerHTML = `
      <div class="flex gap-1 h-2 rounded overflow-hidden bg-slate-800">
        ${parts
          .map(
            (p, i) =>
              `<div title="${p[0]}: ${p[1]}ms"
                class="${["bg-indigo-500", "bg-sky-500", "bg-emerald-500", "bg-amber-500"][i]}"
                style="width:${Math.max(2, ((p[1] || 0) / barTotal) * 100)}%"></div>`,
          )
          .join("")}
      </div>
      <div class="text-[10px] text-slate-500 mt-1">
        ${chatMs}ms chat · ${t.embed_ms}ms embed · ${t.multi_hop_ms}ms retrieve ·
        ${t.synthesis_ms}ms synth · total ${t.total_ms}ms ·
        ${retrieval.seed_count} seeds → ${retrieval.final_node_count} nodes
        (k=${retrieval.k}, hops=${retrieval.hops}, think≤${
          retrieval.thinking_max != null ? retrieval.thinking_max : "?"
        }, ${retrieval.strategy})
      </div>`;
  }

  function edgeEndpointIds(d) {
    const s = typeof d.source === "object" && d.source ? d.source.id : d.source;
    const t = typeof d.target === "object" && d.target ? d.target.id : d.target;
    return [String(s), String(t)];
  }

  function buildQuerySeedVisual(payload) {
    const q = String(payload.query || "").trim();
    const ep = payload.entry_plan;
    const subs =
      ep && Array.isArray(ep.sub_queries)
        ? ep.sub_queries.map((s) => String(s || "").trim()).filter((s) => s.length)
        : [];
    const uniq = subs.length ? [...new Set(subs)] : q ? [q] : [];
    const lines = (() => {
      if (!uniq.length) return ["(no query)"];
      if (uniq.length === 1) {
        const s = uniq[0];
        return [s.length > 34 ? s.slice(0, 33) + "…" : s];
      }
      if (uniq.length === 2) {
        return uniq.map((s) => (s.length > 30 ? s.slice(0, 29) + "…" : s));
      }
      return [
        `${uniq.length} retrieval seeds`,
        uniq
          .slice(0, 3)
          .map((s) => (s.length > 22 ? s.slice(0, 21) + "…" : s))
          .join(" · ") + (uniq.length > 3 ? " · …" : ""),
      ];
    })();
    const tooltip =
      `Your message:\n${q || "(empty)"}\n\n` +
      `Vector seeds embedded for retrieval (${uniq.length}):\n` +
      uniq.join("\n");
    return { lines, tooltip, uniq };
  }

  function clearGraph() {
    svg.selectAll("*").remove();
  }

  function renderGraph(payload) {
    clearGraph();
    const node = svg.node();
    if (!node) return;
    const width = node.clientWidth;
    const height = node.clientHeight;
    if (!width || !height) return;

    const cited = new Set(payload.answer.cited_node_ids || []);
    const nodeData = (payload.constellation.nodes || []).map((n) => ({
      ...n,
      r: 6 + (n.confidence || 0.4) * 10,
      color: cited.has(n.id) ? "#34d399" : TYPE_COLOR[n.node_type] || "#94a3b8",
    }));
    const seedVis = buildQuerySeedVisual(payload);
    const queryNode = {
      id: "__query__",
      label: payload.query,
      graphLines: seedVis.lines,
      queryTooltip: seedVis.tooltip,
      isQuery: true,
      r: seedVis.lines.length > 1 ? 16 : 14,
      color: "#fbbf24",
      x: width / 2,
      y: height / 2,
      fx: width / 2,
      fy: height / 2,
    };
    const nodes = [queryNode, ...nodeData];
    const realEdges = (payload.constellation.edges || []).map((e) => ({ ...e, kind: "real" }));
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
      .attr("r", (d) => d.r)
      .attr("fill", (d) => d.color)
      .attr("opacity", (d) => (d.isQuery ? 0.95 : 1))
      .attr("stroke", (d) => (d.is_cited ? "#facc15" : "#0f172a"))
      .attr("stroke-width", (d) => (d.is_cited ? 2.2 : 1));

    nodeSel
      .append("title")
      .text(
        (d) =>
          d.isQuery
            ? d.queryTooltip || `query: ${d.label}`
            : `${d.label} [${d.node_type}] conf=${(d.confidence || 0).toFixed(2)}`,
      );

    if (simulation) simulation.stop();
    simulation = d3
      .forceSimulation(nodes)
      .force(
        "link",
        d3
          .forceLink(links)
          .id((d) => d.id)
          .distance((l) => (l.kind === "seed" ? 88 : 58))
          .strength((l) => (l.kind === "seed" ? 0.18 : 0.42)),
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

  function applyPayload(payload) {
    const nNodes = (payload.constellation.nodes || []).length;
    const nConstEdges = (payload.constellation.edges || []).length;
    const nSpokes = Math.min(nNodes, 32);
    const hops = payload.retrieval && payload.retrieval.hops != null ? payload.retrieval.hops : "?";
    const tm =
      payload.retrieval && payload.retrieval.thinking_max != null
        ? payload.retrieval.thinking_max
        : "?";
    setStatus(
      `verdict=${payload.verdict} · ${nNodes} nodes · ${nConstEdges} graph edges · ${nSpokes} query links · hops≤${hops} · think≤${tm}`,
      "ok",
    );
    renderVector(payload.query_embedding_preview);
    renderTiming(payload.timing_ms, payload.retrieval);
    renderGraph(payload);
  }

  async function parseGrowthSse(resp) {
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
        let eventName = null;
        for (const line of block.split("\n")) {
          if (line.startsWith("event:")) {
            eventName = line.slice(6).trim();
            continue;
          }
          if (!line.startsWith("data: ")) continue;
          const raw = line.slice(6);
          let obj;
          try {
            obj = JSON.parse(raw);
          } catch (_) {
            continue;
          }
          if (eventName === "error") {
            throw new Error(obj.message || "error");
          }
          if (obj.type === "error") {
            throw new Error(obj.message || "error");
          }
          if (obj.type === "phase") {
            resetPhases();
            if (obj.phase === "chat_compact") setPhase("chat", true);
            if (obj.phase === "embed") setPhase("embed", true);
            if (obj.phase === "retrieve") setPhase("retrieve", true);
            if (obj.phase === "synthesize") setPhase("synth", true);
          }
          if (obj.type === "complete") {
            finalPayload = obj.payload;
            resetPhases();
          }
          if (eventName === "argus_phase" && obj.phase) {
            const ts = new Date().toISOString().slice(11, 19);
            const c = obj.count != null ? String(obj.count) : "—";
            const ms = obj.elapsed_ms != null ? String(obj.elapsed_ms) : "—";
            appendGrowthLine(`${ts}  ${obj.phase}  count=${c}  ${ms}ms`);
          }
          if (eventName === "trigger_emitted") {
            appendGrowthLine(
              `trigger  ${obj.trigger_id || "?"}  gap=${obj.gap_class || "?"}  strength=${obj.stub_signal_strength ?? "?"}`,
            );
          }
          if (eventName === "argus_complete") {
            appendGrowthLine(
              `argus_complete  outcome=${obj.outcome}  bytes=${obj.bytes_acquired ?? 0}  ingest=${obj.ingest_run_id || "—"}`,
            );
          }
        }
      }
    }
    return finalPayload;
  }

  async function growthAsk(ev) {
    ev.preventDefault();
    ev.stopImmediatePropagation();
    const q = (qEl && qEl.value) || "";
    const trimmed = String(q).trim();
    if (!trimmed) return;
    resetPhases();
    setStatus("connecting (growth)…");
    clearGraph();
    if (logEl) logEl.innerHTML = "";
    let resp;
    try {
      resp = await fetch("/cockpit/api/growth-stream", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
        body: JSON.stringify({
          q: trimmed,
          growth: true,
          k: parseInt(kEl && kEl.value, 10) || 10,
          hops: parseInt(hopsEl && hopsEl.value, 10) || 2,
          thinking_max: thinkingMaxEl
            ? Math.max(0, Math.min(8, parseInt(thinkingMaxEl.value, 10) || 0))
            : 2,
          conversation_summary: "",
          conversation_messages: [],
        }),
      });
    } catch (err) {
      setStatus("network error: " + err, "error");
      return;
    }
    if (!resp.ok) {
      setStatus("HTTP " + resp.status, "error");
      return;
    }
    let payload;
    try {
      payload = await parseGrowthSse(resp);
    } catch (e) {
      setStatus(String(e.message || e), "error");
      resetPhases();
      return;
    }
    if (!payload) {
      setStatus("empty stream", "error");
      resetPhases();
      return;
    }
    if (payload.error) {
      setStatus(payload.error, "error");
      resetPhases();
      return;
    }
    if (qEl) qEl.value = "";
    applyPayload(payload);
  }

  form.addEventListener("submit", growthAsk, true);
})();
