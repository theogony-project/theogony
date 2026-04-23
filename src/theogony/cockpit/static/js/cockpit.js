document.body.addEventListener("htmx:afterSwap", function () {
  if (document.getElementById("cluster-graph") && window.__cockpitMountCluster) {
    window.__cockpitMountCluster();
  }
  if (document.getElementById("hover-lupe") && window.__cockpitMountHoverLupe) {
    window.__cockpitMountHoverLupe();
  }
});
