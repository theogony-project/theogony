(function () {
  const url = "/cockpit/sse/status";
  try {
    const es = new EventSource(url);
    es.addEventListener("status_tick", function (event) {
      let data;
      try { data = JSON.parse(event.data); } catch (_) { return; }
      document.querySelectorAll("[data-status-key]").forEach(function (el) {
        const key = el.getAttribute("data-status-key");
        if (!key || !(key in data)) return;
        el.textContent = String(data[key]);
      });
    });
  } catch (_) {}
})();
