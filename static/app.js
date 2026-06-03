const form = document.getElementById("analyze-form");
const textInput = document.getElementById("text-input");
const fileInput = document.getElementById("file-input");
const fileNameEl = document.getElementById("file-name");
const errorMsg = document.getElementById("error-msg");
const loading = document.getElementById("loading");
const results = document.getElementById("results");
const submitBtn = document.getElementById("submit-btn");
const apiStatus = document.getElementById("api-status");
const matrixWrap = document.getElementById("matrix-table-wrap");
const graphContainer = document.getElementById("graph-network");
const graphStats = document.getElementById("graph-stats");
const downloadBtn = document.getElementById("download-btn");

let networkInstance = null;
let analysisResult = null;
let activeTab = "cooccurrence";

const TAB_ACCENT = {
  cooccurrence: { node: "#2a7d72", edge: "#8ab5ad", hi: "#e8f2f0" },
  semantic: { node: "#4f5fae", edge: "#9aa5d4", hi: "#eef0f8" },
  epistemic: { node: "#b85a52", edge: "#d4a09a", hi: "#f8eeec" },
};

const DOWNLOAD_NAMES = {
  cooccurrence: "cooccurrence_matrix.csv",
  semantic: "semantic_matrix.csv",
  epistemic: "epistemic_matrix.csv",
};

const METHOD_NOTES = {
  cooccurrence: {
    title: "Co-occurrence",
    body: `Counts how often two concepts appear in the <em>same sentence</em> (stanza). Cell (i, j) is the number of sentences where both concepts are active; the diagonal is how often a concept appears in any sentence. The network shows direct topical proximity in the text—concepts that are talked about together in one utterance.`,
  },
  semantic: {
    title: "Semantic",
    body: `Builds a <em>distributional</em> similarity matrix. Each sentence is a document; each concept gets a TF‑IDF profile across sentences. Cell (i, j) is the cosine similarity between those profiles—high values mean the concepts tend to appear in similar contexts even when not in the same sentence. The graph keeps the strongest similarity links only.`,
  },
  epistemic: {
    title: "Epistemic (ENA-style)",
    body: `Inspired by Epistemic Network Analysis. Links concepts that co‑activate in the same sentence, plus weaker links between <em>consecutive</em> sentences (lag weight 0.5). The matrix is then <em>centered</em>: observed links minus expected links from marginal frequencies. Positive values = more connected than chance; negative = less than expected. Green/red edges in the graph show sign.`,
  },
};

function setAccent(tabKey) {
  results.dataset.accent = tabKey;
}

function renderMethodNote(tabKey) {
  const el = document.getElementById("method-note");
  const note = METHOD_NOTES[tabKey];
  if (!el || !note) return;
  el.innerHTML = `<strong>${note.title}</strong>${note.body}`;
}

async function checkHealth() {
  try {
    const res = await fetch("/api/health");
    const data = await res.json();
    if (!data.openai_configured) {
      apiStatus.hidden = false;
      apiStatus.textContent = "API key missing";
    }
  } catch {
    apiStatus.hidden = false;
    apiStatus.textContent = "Server unavailable";
  }
}

function showError(message) {
  errorMsg.hidden = !message;
  errorMsg.textContent = message || "";
}

function setLoading(on) {
  loading.classList.toggle("is-active", on);
  loading.hidden = !on;
  submitBtn.disabled = on;
}

setLoading(false);

fileInput.addEventListener("change", () => {
  const file = fileInput.files?.[0];
  if (!file) return;
  fileNameEl.textContent = file.name;
  const reader = new FileReader();
  reader.onload = () => {
    textInput.value = reader.result;
  };
  reader.readAsText(file, "UTF-8");
});

function renderConcepts(data) {
  const grid = document.getElementById("concepts-by-sentence");
  grid.innerHTML = "";
  data.concepts_by_sentence.forEach((words, i) => {
    const p = document.createElement("p");
    p.textContent = `${i + 1}. ${words.join(", ") || "—"}`;
    grid.appendChild(p);
  });

  const tbody = document.querySelector("#freq-table tbody");
  tbody.innerHTML = "";
  (data.concept_frequency || []).forEach(({ concept, count }) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${escapeHtml(concept)}</td><td>${count}</td>`;
    tbody.appendChild(tr);
  });
}

function escapeHtml(s) {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function formatCell(v, key) {
  if (key === "semantic") return Number(v).toFixed(3);
  if (key === "epistemic") return Number(v).toFixed(2);
  return Number(v) % 1 === 0 ? String(Math.round(v)) : Number(v).toFixed(2);
}

function renderGraph(tabKey) {
  const graph = analysisResult?.graphs?.[tabKey];
  const accent = TAB_ACCENT[tabKey] || TAB_ACCENT.cooccurrence;

  if (!graph || typeof vis === "undefined") {
    graphStats.textContent = "";
    graphContainer.innerHTML = "";
    if (networkInstance) {
      networkInstance.destroy();
      networkInstance = null;
    }
    return;
  }

  const { nodes, edges, stats } = graph;
  graphStats.textContent = `${stats.node_count} nodes · ${stats.edge_count} edges`;

  const visNodes = new vis.DataSet(
    nodes.map((n) => ({
      id: n.id,
      label: n.label,
      value: n.value,
      title: n.title,
      font: { color: "#1a1917", face: "Sora", size: 13 },
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
      color: edgeColors[e.polarity] || edgeColors.neutral,
    }))
  );

  if (networkInstance) networkInstance.destroy();

  networkInstance = new vis.Network(
    graphContainer,
    { nodes: visNodes, edges: visEdges },
    {
      physics: {
        stabilization: { iterations: 100 },
        barnesHut: { gravitationalConstant: -2200, springLength: 120 },
      },
      interaction: { hover: true, navigationButtons: false },
      edges: { smooth: { type: "continuous" }, width: 1 },
      nodes: { shape: "dot", scaling: { min: 10, max: 28 } },
    }
  );
}

function renderMatrix(tabKey) {
  if (!analysisResult?.matrices?.[tabKey]) return;
  setAccent(tabKey);
  renderMethodNote(tabKey);
  const { labels, values } = analysisResult.matrices[tabKey];
  renderGraph(tabKey);

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
      if (v >= threshold && v > 0) td.classList.add("high");
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });
  table.appendChild(tbody);

  matrixWrap.innerHTML = "";
  matrixWrap.appendChild(table);
}

document.querySelectorAll(".tab").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((b) => b.classList.remove("on"));
    btn.classList.add("on");
    activeTab = btn.dataset.tab;
    renderMatrix(activeTab);
  });
});

function matrixToCsv(labels, values) {
  const header = ["", ...labels].map((c) => `"${String(c).replace(/"/g, '""')}"`);
  const lines = [header.join(",")];
  labels.forEach((row, i) => {
    const cells = [
      `"${String(row).replace(/"/g, '""')}"`,
      ...values[i].map((v) => String(v)),
    ];
    lines.push(cells.join(","));
  });
  return "\uFEFF" + lines.join("\n");
}

downloadBtn.addEventListener("click", () => {
  const m = analysisResult?.matrices?.[activeTab];
  if (!m) return;
  const csv = matrixToCsv(m.labels, m.values);
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = DOWNLOAD_NAMES[activeTab] || "matrix.csv";
  a.click();
  URL.revokeObjectURL(url);
});

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  showError("");
  const text = textInput.value.trim();
  if (text.length < 20) {
    showError("Enter at least 20 characters.");
    return;
  }

  const fd = new FormData();
  fd.append("text", text);
  fd.append("min_freq", document.getElementById("min-freq").value || "2");

  setLoading(true);
  try {
    const res = await fetch("/api/analyze", { method: "POST", body: fd });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || "Analysis failed");

    analysisResult = data;
    document.getElementById("stat-sentences").textContent = data.sentence_count;
    document.getElementById("stat-vocab").textContent = data.vocabulary_size;
    renderConcepts(data);
    renderMatrix(activeTab);
    results.hidden = false;
    downloadBtn.disabled = false;
    results.scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (err) {
    showError(err.message || String(err));
  } finally {
    setLoading(false);
  }
});

document.getElementById("sample-btn").addEventListener("click", async () => {
  try {
    const res = await fetch("/api/sample");
    if (res.ok) textInput.value = await res.text();
  } catch {
    showError("Could not load sample.");
  }
});

checkHealth();
