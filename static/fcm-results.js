/**
 * Render FCM pipeline results (concepts, edges, matrix, graph).
 */

import { downloadMatrixXlsx, escapeHtml } from "./analysis-shared.js";

const FCM_ACCENT = { node: "#5a4a8a", edge: "#8a7aad", hi: "#eeeaf8" };

const fcmNetworks = new Map();

export function destroyFcmNetworks() {
  fcmNetworks.forEach((net) => net?.destroy?.());
  fcmNetworks.clear();
}

function formatFcmCell(v) {
  const n = Number(v);
  if (n === 0) return "0";
  return n > 0 ? `+${n}` : String(n);
}

function buildFcmMatrixTable(matrix) {
  const { labels, values } = matrix;
  const table = document.createElement("table");
  table.className = "matrix-table";

  const thead = document.createElement("thead");
  const headRow = document.createElement("tr");
  headRow.innerHTML =
    '<th class="corner">source ↓ target →</th>' +
    labels.map((l) => `<th>${escapeHtml(l)}</th>`).join("");
  thead.appendChild(headRow);
  table.appendChild(thead);

  const tbody = document.createElement("tbody");
  labels.forEach((rowLabel, i) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td class="row-head">${escapeHtml(rowLabel)}</td>`;
    values[i].forEach((v) => {
      const td = document.createElement("td");
      td.textContent = formatFcmCell(v);
      if (v < 0) td.classList.add("negative");
      else if (v > 0) td.classList.add("high");
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });
  table.appendChild(tbody);
  return table;
}

function mountFcmNetwork(container, graph, cardKey) {
  const prev = fcmNetworks.get(cardKey);
  if (prev) prev.destroy();

  if (!graph || typeof vis === "undefined") {
    container.innerHTML = "";
    fcmNetworks.delete(cardKey);
    return null;
  }

  const { nodes, edges, stats } = graph;
  const visNodes = new vis.DataSet(
    nodes.map((n) => ({
      id: n.id,
      label: n.label,
      value: n.value,
      title: n.title,
      font: { color: "#121110", face: "IBM Plex Mono", size: 11 },
      color: {
        background: "#fff",
        border: FCM_ACCENT.node,
        highlight: { background: FCM_ACCENT.hi, border: FCM_ACCENT.node },
      },
    }))
  );

  const edgeColors = {
    positive: { color: "#3d8f6e", highlight: "#2a7d72" },
    negative: { color: "#c45c5c", highlight: "#9a4841" },
  };

  const visEdges = new vis.DataSet(
    edges.map((e, idx) => ({
      id: idx,
      from: e.from,
      to: e.to,
      value: e.value,
      title: e.title,
      arrows: { to: { enabled: true, scaleFactor: 0.55 } },
      color: edgeColors[e.polarity] || edgeColors.positive,
      dashes: e.polarity === "negative",
      width: 1 + Math.abs(e.weight || 1),
    }))
  );

  const network = new vis.Network(
    container,
    { nodes: visNodes, edges: visEdges },
    {
      physics: {
        stabilization: { iterations: 80 },
        barnesHut: { gravitationalConstant: -2000, springLength: 110 },
      },
      interaction: { hover: true, navigationButtons: false },
      edges: { smooth: { type: "continuous" } },
      nodes: { shape: "dot", scaling: { min: 8, max: 24 } },
    }
  );

  fcmNetworks.set(cardKey, network);
  return { network, stats };
}

/**
 * @returns {{ tryMountGraph: () => object|null, cardKey: string }}
 */
export function renderFcmResults(data, rootEl, opts = {}) {
  if (!rootEl) return { tryMountGraph: () => null, cardKey: "" };

  const reviewIndex = opts.reviewIndex ?? 0;
  const cardKey = opts.cardKey || `fcm-${reviewIndex}`;
  const xlsxName = opts.xlsxName || `review${reviewIndex + 1}_fcm_adjacency_matrix.xlsx`;
  const pngName = opts.pngName || `review${reviewIndex + 1}_fcm_network.png`;

  rootEl.innerHTML = "";

  const lang = data.language || {};
  const langBadge = document.createElement("p");
  langBadge.className = "meta readout fcm-lang-badge";
  const trNote = lang.translated
    ? `${lang.detected} → EN`
    : `${lang.detected || "en"} · no translation`;
  langBadge.innerHTML = `
    <span class="readout-key">LANG</span> ${escapeHtml(trNote)}
    <span class="readout-sep">│</span>
    <span class="readout-key">TONE</span> ${escapeHtml(data.review_tone || "—")}
    <span class="readout-sep">│</span>
    <span class="readout-key">CONCEPTS</span> ${data.vocabulary_size ?? "—"}
    <span class="readout-sep">│</span>
    <span class="readout-key">EDGES</span> ${(data.edges || []).length}
  `;
  rootEl.appendChild(langBadge);

  const conceptsFold = document.createElement("details");
  conceptsFold.className = "fold";
  conceptsFold.open = true;
  conceptsFold.innerHTML = "<summary>[ EXPAND ] Thematic concept codebook</summary>";

  const codebook = document.createElement("p");
  codebook.className = "concept-lines";
  codebook.textContent = (data.concepts || []).map((c) => c.label).join(" · ") || "—";
  conceptsFold.appendChild(codebook);

  if ((data.concepts_by_sentence || []).length) {
    const bySent = document.createElement("div");
    bySent.className = "concept-lines muted-lines";
    (data.concepts_by_sentence || []).forEach((row, i) => {
      const p = document.createElement("p");
      p.textContent = `${i + 1}. ${(row || []).join(", ") || "—"}`;
      bySent.appendChild(p);
    });
    conceptsFold.appendChild(bySent);
  } else {
    const conceptTable = document.createElement("table");
    conceptTable.className = "data-table fcm-edge-table";
    conceptTable.innerHTML = "<thead><tr><th>concept</th><th>phrases</th></tr></thead>";
    const cbody = document.createElement("tbody");
    (data.concepts || []).forEach((c) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td>${escapeHtml(c.label)}</td><td>${escapeHtml((c.phrases || []).join(" · "))}</td>`;
      cbody.appendChild(tr);
    });
    conceptTable.appendChild(cbody);
    conceptsFold.appendChild(conceptTable);
  }
  rootEl.appendChild(conceptsFold);

  const edgesTitle = document.createElement("p");
  edgesTitle.className = "fold-label";
  edgesTitle.textContent = "FCM EDGES (causal influences)";
  rootEl.appendChild(edgesTitle);

  const edgeTable = document.createElement("table");
  edgeTable.className = "data-table fcm-edge-table";
  edgeTable.innerHTML = `
    <thead>
      <tr>
        <th>source</th><th>target</th><th>w</th><th>str</th>
        <th>evidence</th><th>analyst note</th>
      </tr>
    </thead>
  `;
  const ebody = document.createElement("tbody");
  (data.edges || []).forEach((e) => {
    const tr = document.createElement("tr");
    const w = Number(e.weight);
    tr.innerHTML = `
      <td>${escapeHtml(e.source)}</td>
      <td>${escapeHtml(e.target)}</td>
      <td class="${w < 0 ? "negative" : "high"}">${w > 0 ? "+" : ""}${w}</td>
      <td>${escapeHtml(e.strength || "")}</td>
      <td class="evidence-cell">${escapeHtml(e.evidence_sentence || "")}</td>
      <td class="note-cell">${escapeHtml(e.analyst_note || "")}</td>
    `;
    ebody.appendChild(tr);
  });
  edgeTable.appendChild(ebody);
  rootEl.appendChild(edgeTable);

  const head = document.createElement("div");
  head.className = "output-head";
  const statsEl = document.createElement("span");
  statsEl.className = "hint readout fcm-graph-stats";
  const actions = document.createElement("div");
  actions.className = "output-actions";
  const dlPng = document.createElement("button");
  dlPng.type = "button";
  dlPng.className = "btn-text fcm-dl-png";
  dlPng.textContent = "[ PNG ]";
  const dlXlsx = document.createElement("button");
  dlXlsx.type = "button";
  dlXlsx.className = "btn-text fcm-dl-xlsx";
  dlXlsx.textContent = "[ XLSX ]";
  actions.appendChild(dlPng);
  actions.appendChild(dlXlsx);
  head.appendChild(statsEl);
  head.appendChild(actions);
  rootEl.appendChild(head);

  const graphFrame = document.createElement("div");
  graphFrame.className = "viz-frame";
  graphFrame.innerHTML = '<span class="viz-label">FCM GRAPH VIEWPORT</span>';
  const graphEl = document.createElement("div");
  graphEl.className = "graph fcm-review-graph";
  graphFrame.appendChild(graphEl);
  rootEl.appendChild(graphFrame);

  const matrixFrame = document.createElement("div");
  matrixFrame.className = "viz-frame";
  matrixFrame.innerHTML = '<span class="viz-label">ADJACENCY MATRIX</span>';
  const matrixWrap = document.createElement("div");
  matrixWrap.className = "matrix-scroll";
  if (data.matrix) matrixWrap.appendChild(buildFcmMatrixTable(data.matrix));
  matrixFrame.appendChild(matrixWrap);
  rootEl.appendChild(matrixFrame);

  let graphMounted = false;

  function tryMountGraph() {
    if (graphMounted) {
      const net = fcmNetworks.get(cardKey);
      if (net) net.redraw?.();
      return fcmNetworks.get(cardKey);
    }
    const mounted = mountFcmNetwork(graphEl, data.graph, cardKey);
    graphMounted = Boolean(mounted);
    if (mounted?.stats) {
      statsEl.textContent = `${mounted.stats.node_count} nodes · ${mounted.stats.edge_count} edges`;
    } else if (!data.graph?.nodes?.length) {
      statsEl.textContent = "no edges inferred";
    }
    return mounted;
  }

  dlXlsx.addEventListener("click", async () => {
    if (!data.matrix) {
      alert("No matrix to download.");
      return;
    }
    try {
      await downloadMatrixXlsx(data.matrix, xlsxName);
    } catch (err) {
      alert(err.message || String(err));
    }
  });

  dlPng.addEventListener("click", () => {
    const net = fcmNetworks.get(cardKey);
    if (!net?.canvas?.frame?.canvas) {
      tryMountGraph();
    }
    const ready = fcmNetworks.get(cardKey);
    if (!ready?.canvas?.frame?.canvas) {
      alert("Open this review card to render the graph, then download PNG.");
      return;
    }
    ready.stopSimulation();
    const url = ready.canvas.frame.canvas.toDataURL("image/png");
    const a = document.createElement("a");
    a.href = url;
    a.download = pngName;
    a.click();
  });

  if (!opts.deferMount) {
    requestAnimationFrame(() => requestAnimationFrame(() => tryMountGraph()));
  }

  return { tryMountGraph, cardKey, graphEl };
}

export function renderFcmCard(bodyEl, analysis, opts = {}) {
  const reviewIndex = opts.reviewIndex ?? 0;
  const detailsEl = opts.detailsEl || null;
  const rendered = renderFcmResults(analysis, bodyEl, {
    reviewIndex,
    cardKey: `fcm-review-${reviewIndex}`,
    xlsxName: `review${reviewIndex + 1}_fcm_adjacency_matrix.xlsx`,
    pngName: `review${reviewIndex + 1}_fcm_network.png`,
    deferMount: true,
  });

  const scheduleMount = () => {
    requestAnimationFrame(() => requestAnimationFrame(() => rendered.tryMountGraph()));
  };

  if (detailsEl) {
    detailsEl.addEventListener("toggle", () => {
      if (detailsEl.open) scheduleMount();
    });
    if (detailsEl.open) scheduleMount();
  } else {
    scheduleMount();
  }

  return rendered;
}
