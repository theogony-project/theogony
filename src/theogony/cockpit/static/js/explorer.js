/* Pantheon Explorer — streamed phases + d3 force-graph + chronicle append. */

(function () {
  const root = document.getElementById("explorer-root");
  const form = document.getElementById("explorer-form");
  const qEl = document.getElementById("explorer-q");
  const kEl = document.getElementById("explorer-k");
  const hopsEl = document.getElementById("explorer-hops");
  const thinkingMaxEl = document.getElementById("explorer-thinking-max");
  const statusEl = document.getElementById("explorer-status");
  const vectorEl = document.getElementById("explorer-vector");
  const timingEl = document.getElementById("explorer-timing");
  const saveBtn = document.getElementById("explorer-save");
  const chatThreadEl = document.getElementById("explorer-chat-thread");
  const newChatBtn = document.getElementById("explorer-new-chat");
  const phases = {
    chat: document.getElementById("phase-chat"),
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
  /** @type {{ role: string, content: string, detailHtml?: string }[]} */
  let chatTurns = [];
  let rollingSummary = "";

  const ASSISTANT_WORKING_HTML =
    '<div class="text-slate-400 text-xs flex items-center gap-2 py-0.5">' +
    '<span class="inline-block w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse"></span>' +
    "Working…</div>";

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
    setPhase("chat", false);
    setPhase("embed", false);
    setPhase("retrieve", false);
    setPhase("synth", false);
  }

  function renderChatThread() {
    if (!chatThreadEl) return;
    const emptyEl = document.getElementById("explorer-chat-empty");
    if (emptyEl) {
      emptyEl.classList.toggle("hidden", chatTurns.length > 0);
    }
    chatThreadEl.querySelectorAll(".explorer-chat-msg").forEach((n) => n.remove());
    for (const t of chatTurns) {
      const isUser = t.role === "user";
      const wrap = document.createElement("div");
      wrap.className =
        "explorer-chat-msg flex flex-col gap-0.5 " + (isUser ? "items-end" : "items-start");
      const bubble = document.createElement("div");
      bubble.className = isUser
        ? "max-w-[min(92%,28rem)] rounded-2xl rounded-br-md border border-sky-700/40 bg-sky-950/50 px-3 py-2 text-sm text-sky-50/95 shadow-sm"
        : "max-w-[min(98%,36rem)] w-full rounded-2xl rounded-bl-md border border-slate-600/50 bg-slate-900/80 px-3 py-2.5 text-sm text-slate-100 shadow-sm";
      const lab = document.createElement("div");
      lab.className =
        "text-[10px] uppercase tracking-wide text-slate-500 mb-0.5 " + (isUser ? "text-right" : "");
      lab.textContent = isUser ? "You" : "Chronicle";
      const body = document.createElement("div");
      body.className =
        "leading-snug break-words text-[13px] [&_a]:text-amber-300 [&_a:hover]:text-amber-200";
      if (isUser) {
        body.classList.add("whitespace-pre-wrap");
        body.textContent = t.content || "";
      } else if (t.detailHtml) {
        body.innerHTML = t.detailHtml;
      } else {
        body.innerHTML = renderAnswerProse(t.content || "");
      }
      bubble.appendChild(lab);
      bubble.appendChild(body);
      wrap.appendChild(bubble);
      chatThreadEl.appendChild(wrap);
    }
    chatThreadEl.scrollTop = chatThreadEl.scrollHeight;
  }

  function resetExplorerChat() {
    chatTurns = [];
    rollingSummary = "";
    renderChatThread();
    clearGraph();
    lastPayload = null;
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
                style="width:${Math.max(2, ((p[1] || 0) / barTotal) * 100)}%"></div>`
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

  /** Labels for the fixed center node: show retrieval seeds, not only the chat line. */
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
            ? d.queryTooltip || `query: ${d.label}`
            : `${d.label} [${d.node_type}] conf=${(d.confidence || 0).toFixed(2)}`
      );

    nodeSel
      .filter((d) => d.is_cited && !d.isQuery)
      .append("text")
      .text((d) => (d.label.length > 28 ? d.label.slice(0, 27) + "…" : d.label))
      .attr("dy", (d) => -d.r - 4)
      .attr("text-anchor", "middle")
      .attr("font-size", 10)
      .attr("fill", "#e2e8f0")
      .attr("pointer-events", "none");

    nodeSel.filter((d) => d.isQuery).each(function (d) {
      const te = d3
        .select(this)
        .append("text")
        .attr("text-anchor", "middle")
        .attr("font-size", 10)
        .attr("fill", "#e2e8f0")
        .attr("pointer-events", "none");
      const lines = d.graphLines && d.graphLines.length ? d.graphLines : [d.label];
      lines.forEach((line, i) => {
        te.append("tspan")
          .attr("x", 0)
          .attr("dy", i === 0 ? -d.r - 4 : 12)
          .text(line);
      });
    });

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
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  function nodeHref(id) {
    return `/cockpit/browser/node/${encodeURIComponent(id)}`;
  }

  function renderAnswerProse(text) {
    if (!text) {
      return "<span class='text-slate-500 italic'>(no answer text)</span>";
    }
    const lines = text.split("\n");
    const html = lines
      .map((raw) => {
        const safe = escapeHtml(raw);
        const linked = safe.replace(
          /\[(AKA-[A-Za-z0-9]+)\]/g,
          (_m, id) =>
            `<a href="${nodeHref(id)}" target="_blank" rel="noopener" class="text-amber-300 hover:text-amber-200 underline decoration-dotted">[${id}]</a>`,
        );
        if (raw.startsWith("- ")) {
          return `<li class="ml-4 list-disc text-slate-200">${linked.slice(2)}</li>`;
        }
        if (raw.trim() === "") return "<div class='h-2'></div>";
        return `<div>${linked}</div>`;
      })
      .join("");
    return `<div class="space-y-1">${html}</div>`;
  }

  function renderCitationChips(payload) {
    const cited = payload.answer.cited_node_ids || [];
    if (!cited.length) return "";
    const byId = new Map((payload.constellation.nodes || []).map((n) => [n.id, n]));
    const chips = cited
      .map((id) => {
        const n = byId.get(id);
        const label = n ? n.label : id;
        return `<a href="${nodeHref(id)}" target="_blank" rel="noopener"
                  class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full
                         border border-emerald-500/40 bg-emerald-950/30 text-emerald-200
                         hover:border-emerald-300 hover:text-emerald-100 transition text-[11px]"
                  title="${escapeHtml(id)}">
                  <span class="w-1.5 h-1.5 rounded-full bg-emerald-400"></span>
                  ${escapeHtml(label.length > 48 ? label.slice(0, 47) + "…" : label)}
                </a>`;
      })
      .join("");
    return `<div class="mt-3 pt-2 border-t border-slate-700/50">
              <div class="text-[10px] uppercase tracking-wider text-slate-500 mb-1.5">Citations</div>
              <div class="flex flex-wrap gap-1.5">${chips}</div>
            </div>`;
  }

  function renderRetrievalHopNote(retrieval) {
    const hops = retrieval.hops ?? "?";
    const strat = retrieval.strategy ?? "?";
    const nph = retrieval.nodes_per_hop;
    let body;
    if (Array.isArray(nph) && nph.length) {
      const tm0 =
        retrieval.thinking_max != null && retrieval.thinking_max !== undefined
          ? retrieval.thinking_max
          : "?";
      body = `Nodes per hop: ${nph.join(" → ")} · think≤${tm0}`;
    } else {
      const stratNote =
        strat === "fixed_depth"
          ? `With <code class="text-slate-400">fixed_depth</code> the report does not include a per-hop node list.`
          : "No per-hop node list in this report.";
      const tm =
        retrieval.thinking_max != null && retrieval.thinking_max !== undefined
          ? retrieval.thinking_max
          : "?";
      body =
        `Retrieval: up to <strong>${hops}</strong> hop(s), up to <strong>${tm}</strong> extra thinking round(s) after the first synthesis, strategy <code class="text-slate-400">${strat}</code>. ` +
        `${stratNote} ` +
        `The hop count bounds graph depth in the store; the d3 view shows the merged constellation, not one ring per hop.`;
      const hn = Number(hops);
      if (Number.isFinite(hn) && hn > 1) {
        body += `<br><span class="text-slate-500 mt-1 inline-block">` +
          `<strong>Graph:</strong> dashed links are only from the <strong>query</strong> to hits (one star layer). ` +
          `Further hops use <em>edges between</em> nodes below; if the constellation has <strong>0</strong> graph edges, ` +
          `you will not see a second “hop ring”, but nodes were still found within the <strong>${hn}</strong>-hop budget.</span>`;
      }
    }
    return `<div class="text-slate-400 text-xs mb-2 border-l-2 border-sky-600/55 pl-2 leading-snug">${body}</div>`;
  }

  function buildAssistantDetailHtml(payload) {
    const meta = payload.synthesis_meta || {};
    const isOffline = meta.mode === "offline_citations" || meta.stub_llm === true;
    const banner = isOffline
      ? `<div class="mb-2 rounded border border-sky-600/40 bg-sky-950/35 px-2 py-1.5 text-xs text-sky-100/95 leading-snug">
           <strong>Offline answer</strong> — citations are real vector hits from the Chronicle seed.
           For Claude synthesis: set <code class="text-sky-200/90">ANTHROPIC_API_KEY</code> and restart
           <code class="text-sky-200/90">theogony cockpit serve</code> or <code class="text-sky-200/90">theogony serve</code>.
         </div>`
      : `<div class="mb-2 rounded border border-emerald-600/45 bg-emerald-950/30 px-2 py-1.5 text-xs text-emerald-100/95 leading-snug">
           <strong>LLM synthesis</strong> — provider <code class="text-emerald-200/90">${escapeHtml(meta.llm_provider || "?")}</code>
           ${meta.llm_model_id ? `· <code class="text-emerald-200/90">${escapeHtml(meta.llm_model_id)}</code>` : ""}
         </div>`;
    const gaps =
      payload.constellation.gaps && payload.constellation.gaps.length
        ? `<div class="text-amber-300/90 text-xs mb-2">gaps: ${payload.constellation.gaps.join(", ")}</div>`
        : "";
    const hopNote = payload.retrieval ? renderRetrievalHopNote(payload.retrieval) : "";
    const ep = payload.entry_plan;
    const qRaw = String(payload.query || "").trim();
    const subs =
      ep && Array.isArray(ep.sub_queries)
        ? ep.sub_queries.map((s) => String(s || "").trim()).filter((s) => s.length)
        : [];
    const entryPlanHtml =
      ep && subs.length
        ? `<div class="text-xs mb-2 rounded border border-violet-600/40 bg-violet-950/30 px-2 py-1.5 text-violet-100/95 leading-snug">
             <div class="font-semibold text-violet-200/95">Retrieval seeds (Chronicle entry)</div>
             <ul class="mt-1 ml-1 list-disc list-inside text-slate-200 space-y-0.5 text-[11px]">
               ${subs.map((s) => `<li class="break-words">${escapeHtml(s)}</li>`).join("")}
             </ul>
             ${
               ep.rationale
                 ? `<div class="text-slate-500 mt-1 text-[11px]">${escapeHtml(ep.rationale)}</div>`
                 : ""
             }
             <div class="text-[10px] text-violet-300/80 mt-1">${
               ep.used_llm_planner
                 ? `Entry planner: LLM · ${ep.planner_duration_ms || 0} ms in retrieve.`
                 : isOffline
                   ? "Entry planner needs a non-stub LLM; stub/offline mode only uses your message as the seed."
                   : subs.length > 1 || subs.some((s) => s.toLowerCase() !== qRaw.toLowerCase())
                     ? "Planner did not run as LLM (parse/timeout fallback); seeds may be widened heuristics or a single line."
                     : "Chronicle entry planner did not run for this request (env disabled it, planner parse/timeout fallback, or similar). Stock server default is planner on with a real LLM; remove THEOGONY_RETRIEVAL__CHRONICLE_ENTRY_PLANNER__ENABLED=false if set."
             }</div>
           </div>`
        : "";
    const proseHtml = renderAnswerProse(payload.answer.text || "");
    const chips = renderCitationChips(payload);
    return (
      banner +
      hopNote +
      entryPlanHtml +
      gaps +
      `<div class="mt-2 border-t border-slate-600/45 pt-2">` +
      `<div class="text-[10px] uppercase tracking-wider text-slate-500 mb-1">Answer (synthesis)</div>` +
      `<div class="text-slate-100 text-sm">${proseHtml}</div>` +
      chips +
      `</div>`
    );
  }

  function assistantErrorDetailHtml(title, raw) {
    const body = escapeHtml(String(raw !== undefined && raw !== null ? raw : "").slice(0, 4000));
    return (
      `<div class="rounded border border-rose-700/45 bg-rose-950/35 px-2.5 py-2 text-rose-100/95 text-sm">` +
      `<div class="font-semibold text-rose-200/95">${escapeHtml(title)}</div>` +
      (body
        ? `<pre class="mt-1 text-xs text-rose-200/85 whitespace-pre-wrap font-mono">${body}</pre>`
        : "") +
      `</div>`
    );
  }

  function applyPayload(payload) {
    lastPayload = payload;
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
            if (obj.phase === "chat_compact") setPhase("chat", true);
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
    const priorForApi = chatTurns.map((t) => ({ role: t.role, content: t.content }));
    chatTurns.push({ role: "user", content: q });
    chatTurns.push({ role: "assistant", content: "", detailHtml: ASSISTANT_WORKING_HTML });
    renderChatThread();
    resetPhases();
    setStatus("connecting…");
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
          thinking_max: thinkingMaxEl
            ? Math.max(0, Math.min(8, parseInt(thinkingMaxEl.value, 10) || 0))
            : 2,
          conversation_summary: rollingSummary || "",
          conversation_messages: priorForApi,
        }),
      });
    } catch (err) {
      setStatus("network error: " + err, "error");
      chatTurns.pop();
      chatTurns.push({
        role: "assistant",
        content: "",
        detailHtml: assistantErrorDetailHtml("Network error", err),
      });
      renderChatThread();
      return;
    }
    if (!resp.ok) {
      setStatus("HTTP " + resp.status, "error");
      let errTxt = "";
      try {
        errTxt = await resp.text();
      } catch (_) {
        /* ignore */
      }
      chatTurns.pop();
      chatTurns.push({
        role: "assistant",
        content: "",
        detailHtml: assistantErrorDetailHtml(`HTTP ${resp.status}`, errTxt || "(no body)"),
      });
      renderChatThread();
      return;
    }
    let payload;
    try {
      payload = await parseSseStream(resp);
    } catch (e) {
      setStatus(String(e.message || e), "error");
      chatTurns.pop();
      chatTurns.push({
        role: "assistant",
        content: "",
        detailHtml: assistantErrorDetailHtml("Stream error", e.message || e),
      });
      renderChatThread();
      resetPhases();
      return;
    }
    if (!payload) {
      setStatus("empty stream", "error");
      chatTurns.pop();
      chatTurns.push({
        role: "assistant",
        content: "",
        detailHtml: assistantErrorDetailHtml(
          "Empty stream",
          "The server closed the stream without a result.",
        ),
      });
      renderChatThread();
      resetPhases();
      return;
    }
    if (payload.error) {
      setStatus(payload.error, "error");
      chatTurns.pop();
      chatTurns.push({
        role: "assistant",
        content: "",
        detailHtml: assistantErrorDetailHtml("Explorer error", payload.error),
      });
      renderChatThread();
      resetPhases();
      return;
    }
    chatTurns.pop();
    chatTurns.pop();
    const ch = payload.chat || {};
    if (Array.isArray(ch.prior_messages_kept)) {
      chatTurns = ch.prior_messages_kept.map((x) => ({
        role: x.role,
        content: String(x.content || ""),
      }));
    } else {
      chatTurns = priorForApi.map((x) => ({ role: x.role, content: String(x.content || "") }));
    }
    chatTurns.push({ role: "user", content: q });
    chatTurns.push({
      role: "assistant",
      content: (payload.answer && payload.answer.text) || "",
      detailHtml: buildAssistantDetailHtml(payload),
    });
    rollingSummary = typeof ch.rolling_summary === "string" ? ch.rolling_summary : rollingSummary;
    renderChatThread();
    qEl.value = "";
    applyPayload(payload);
  }

  async function saveHypothesis() {
    if (!lastPayload || sampleOnly || !appendEnabled) return;
    let q = lastPayload.query || "";
    for (let i = chatTurns.length - 1; i >= 0; i--) {
      if (chatTurns[i].role === "user") {
        q = chatTurns[i].content;
        break;
      }
    }
    const ans = (lastPayload.answer && lastPayload.answer.text) || "";
    const body =
      (ans.trim() ? ans : "") +
      (ans.trim() && q ? "\n\n—\n\n" : "") +
      (q ? `Question:\n${q}` : "");
    const title = (q.length > 80 ? q.slice(0, 77) + "…" : q) || "Explorer hypothesis";
    setStatus("writing to Chronicle…");
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
  if (newChatBtn) newChatBtn.addEventListener("click", resetExplorerChat);

  document.querySelectorAll("#explorer-examples .explorer-example").forEach((btn) => {
    btn.addEventListener("click", () => {
      const q = btn.getAttribute("data-q") || "";
      if (!q) return;
      qEl.value = q;
      qEl.focus();
      form.requestSubmit();
    });
  });
})();
