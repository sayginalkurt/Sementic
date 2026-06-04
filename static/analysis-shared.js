/** Shared constants and DOM helpers for analysis views. */

export const TAB_KEYS = ["cooccurrence", "semantic", "epistemic"];

export const TAB_ACCENT = {
  cooccurrence: { node: "#2a7d72", edge: "#8ab5ad", hi: "#e8f2f0" },
  semantic: { node: "#4f5fae", edge: "#9aa5d4", hi: "#eef0f8" },
  epistemic: { node: "#b85a52", edge: "#d4a09a", hi: "#f8eeec" },
};

export const MATRIX_DOWNLOAD_NAMES = {
  cooccurrence: "cooccurrence_matrix.xlsx",
  semantic: "semantic_matrix.xlsx",
  epistemic: "epistemic_matrix.xlsx",
};

export function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

export function formatCell(v, key) {
  const n = Number(v);
  if (n === 0) return "0";
  if (key === "semantic") return n.toFixed(3);
  if (key === "epistemic" || n < 0) return n.toFixed(2);
  return n % 1 === 0 ? String(Math.round(n)) : n.toFixed(2);
}

export function edgeArrows(direction) {
  const scale = 0.55;
  if (direction === "b_to_a") {
    return { from: { enabled: true, scaleFactor: scale } };
  }
  if (direction === "mutual") {
    return {
      to: { enabled: true, scaleFactor: scale },
      from: { enabled: true, scaleFactor: scale },
    };
  }
  return { to: { enabled: true, scaleFactor: scale } };
}

export function buildMatrixTable(matrix, tabKey) {
  const { labels, values } = matrix;
  let max = -Infinity;
  values.forEach((row) =>
    row.forEach((v) => {
      if (v > max) max = v;
    })
  );
  const threshold = max * 0.6;

  const table = document.createElement("table");
  table.className = "matrix-table";

  const thead = document.createElement("thead");
  const headRow = document.createElement("tr");
  headRow.innerHTML =
    '<th class="corner"></th>' +
    labels.map((l) => `<th>${escapeHtml(l)}</th>`).join("");
  thead.appendChild(headRow);
  table.appendChild(thead);

  const tbody = document.createElement("tbody");
  labels.forEach((rowLabel, i) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td class="row-head">${escapeHtml(rowLabel)}</td>`;
    values[i].forEach((v) => {
      const td = document.createElement("td");
      td.textContent = formatCell(v, tabKey);
      if (v < 0) td.classList.add("negative");
      else if (v >= threshold && v > 0) td.classList.add("high");
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });
  table.appendChild(tbody);
  return table;
}

export function mountNetwork(container, graph, tabKey) {
  if (!graph || typeof vis === "undefined") {
    container.innerHTML = "";
    return null;
  }

  const accent = TAB_ACCENT[tabKey] || TAB_ACCENT.cooccurrence;
  const { nodes, edges } = graph;

  const visNodes = new vis.DataSet(
    nodes.map((n) => ({
      id: n.id,
      label: n.label,
      value: n.value,
      title: n.title,
      font: { color: "#1a1917", face: "Sora", size: 12 },
      color: {
        background: "#fff",
        border: accent.node,
        highlight: { background: accent.hi, border: accent.node },
      },
    }))
  );

  const edgeColors = {
    neutral: { color: accent.edge, highlight: accent.node },
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
      arrows: edgeArrows(e.direction),
      color: edgeColors[e.polarity] || edgeColors.neutral,
      dashes: e.polarity === "negative",
    }))
  );

  return new vis.Network(
    container,
    { nodes: visNodes, edges: visEdges },
    {
      physics: {
        stabilization: { iterations: 80 },
        barnesHut: { gravitationalConstant: -2000, springLength: 110 },
      },
      interaction: { hover: true, navigationButtons: false },
      edges: { smooth: { type: "continuous" }, width: 1 },
      nodes: { shape: "dot", scaling: { min: 8, max: 24 } },
    }
  );
}

export async function downloadMatrixXlsx(matrix, filename) {
  const res = await fetch("/api/download/xlsx", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      labels: matrix.labels,
      values: matrix.values,
      filename: filename || "matrix.xlsx",
    }),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || "Download failed");
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename || "matrix.xlsx";
  a.click();
  URL.revokeObjectURL(url);
}
