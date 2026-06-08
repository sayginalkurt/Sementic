/**
 * CH-C: Google Drive / local dataset — respondent list + per-row analysis.
 */

import {
  TAB_KEYS,
  MATRIX_DOWNLOAD_NAMES,
  escapeHtml,
  buildMatrixTable,
  mountNetwork,
  downloadMatrixXlsx,
} from "./analysis-shared.js";
import { consumeNdjsonStream } from "./stream-client.js";
import { stepsForPipeline } from "./workflow-steps.js";
import { renderFcmCard, destroyFcmNetworks } from "./fcm-results.js";

const configMsg = document.getElementById("dataset-config-msg");
const ui = document.getElementById("dataset-ui");
const loadingEl = document.getElementById("dataset-loading");
const analyzeLoadingEl = document.getElementById("dataset-analyze-loading");
const searchInput = document.getElementById("dataset-search");
const tbody = document.querySelector("#respondents-table tbody");
const sourceLabel = document.getElementById("dataset-source-label");
const resultsRoot = document.getElementById("dataset-results-root");
const fullFold = document.getElementById("dataset-full-fold");
const fullWrap = document.getElementById("dataset-full-wrap");
const fullLoadingEl = document.getElementById("dataset-full-loading");

const COMPARISON_FIELDS = [
  { key: "n_concepts", label: "n_concepts", pipeline: true },
  { key: "n_relationships", label: "n_relationships", pipeline: true },
  { key: "concepts", label: "concepts", pipeline: true },
];

let searchTimer = null;
let networkInstance = null;
let analyzing = false;
let fullDatasetLoaded = false;

function showMsg(text, isError = false) {
  configMsg.hidden = !text;
  configMsg.textContent = text || "";
  configMsg.classList.toggle("error", isError);
}

function setListLoading(on) {
  loadingEl.hidden = !on;
}

function setAnalyzeLoading(on) {
  analyzeLoadingEl.hidden = !on;
  analyzing = on;
  tbody.querySelectorAll(".analyze-row-btn").forEach((btn) => {
    btn.disabled = on;
  });
}

function destroyResultNetwork() {
  networkInstance?.destroy?.();
  networkInstance = null;
  destroyFcmNetworks();
}

async function loadRespondents(q = "") {
  setListLoading(true);
  try {
    const url = q
      ? `/api/dataset/respondents?q=${encodeURIComponent(q)}`
      : "/api/dataset/respondents";
    const res = await fetch(url);
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || "Failed to load respondents");
    renderTable(data);
  } catch (err) {
    showMsg(err.message || String(err), true);
  } finally {
    setListLoading(false);
  }
}

function fmtCell(val) {
  if (val == null || val === "") return "—";
  return String(val);
}

function renderFullDatasetTable(data) {
  if (!fullWrap) return;
  const cols = data.columns || [];
  const rows = data.rows || [];
  if (!cols.length) {
    fullWrap.innerHTML = "<p class=\"hint\">No data.</p>";
    return;
  }

  const table = document.createElement("table");
  table.className = "data-table dataset-full-table";
  const thead = document.createElement("thead");
  const headRow = document.createElement("tr");
  cols.forEach((col) => {
    const th = document.createElement("th");
    th.textContent = col;
    if (col === "open_ended_response") th.classList.add("open-ended-col");
    headRow.appendChild(th);
  });
  thead.appendChild(headRow);
  table.appendChild(thead);

  const tbody = document.createElement("tbody");
  rows.forEach((row) => {
    const tr = document.createElement("tr");
    cols.forEach((col) => {
      const td = document.createElement("td");
      td.textContent = fmtCell(row[col]);
      if (col === "open_ended_response") td.classList.add("open-ended-col");
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });
  table.appendChild(tbody);
  fullWrap.innerHTML = "";
  fullWrap.appendChild(table);
}

async function loadFullDataset(q = "") {
  if (!fullWrap) return;
  fullLoadingEl.hidden = false;
  try {
    const url = q
      ? `/api/dataset/respondents/full?q=${encodeURIComponent(q)}`
      : "/api/dataset/respondents/full";
    const res = await fetch(url);
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || "Failed to load full dataset");
    renderFullDatasetTable(data);
    fullDatasetLoaded = true;
  } catch (err) {
    fullWrap.innerHTML = `<p class="hint error">${escapeHtml(err.message || String(err))}</p>`;
  } finally {
    fullLoadingEl.hidden = true;
  }
}

function renderComparisonPanel(rootEl, payload) {
  const datasetRef = payload?.dataset_reference || {};
  const pipelineOut = payload?.pipeline_output || {};
  if (!Object.keys(datasetRef).length) return;

  const fold = document.createElement("details");
  fold.className = "fold dataset-compare";
  fold.open = true;
  fold.innerHTML = "<summary>[ EXPAND ] Dataset comparison — reference vs pipeline</summary>";

  const body = document.createElement("div");
  body.className = "dataset-compare-body";

  const table = document.createElement("table");
  table.className = "dataset-compare-table";
  table.innerHTML = `
    <thead>
      <tr>
        <th>Field</th>
        <th class="col-dataset">Dataset (reference)</th>
        <th class="col-pipeline">Pipeline output</th>
      </tr>
    </thead>
  `;
  const tbody = document.createElement("tbody");

  COMPARISON_FIELDS.forEach(({ key, label, pipeline }) => {
    const dsVal = datasetRef[key];
    const plVal = pipeline ? pipelineOut[key] : null;
    const tr = document.createElement("tr");

    let matchClass = "";
    if (pipeline && dsVal != null && plVal != null) {
      if (key === "n_concepts" || key === "n_relationships") {
        matchClass = Number(dsVal) === Number(plVal) ? "match-ok" : "match-diff";
      } else if (key === "concepts") {
        const norm = (s) =>
          String(s || "")
            .split("|")
            .map((x) => x.trim().toLowerCase())
            .filter(Boolean)
            .sort()
            .join("|");
        matchClass = norm(dsVal) === norm(plVal) ? "match-ok" : "match-diff";
      }
    }

    tr.innerHTML = `
      <th>${escapeHtml(label)}</th>
      <td class="col-dataset ${matchClass}">${escapeHtml(fmtCell(dsVal))}</td>
      <td class="col-pipeline">${pipeline ? escapeHtml(fmtCell(plVal)) : "—"}</td>
    `;
    tbody.appendChild(tr);
  });

  table.appendChild(tbody);
  body.appendChild(table);
  fold.appendChild(body);
  rootEl.appendChild(fold);
}

function renderTable(data) {
  sourceLabel.textContent = `SRC: ${data.source.toUpperCase()} · N=${data.count}`;
  tbody.innerHTML = "";

  (data.respondents || []).forEach((r) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${escapeHtml(r.respondent_id)}</td>
      <td>${escapeHtml(r.age ?? "—")}</td>
      <td>${escapeHtml(r.gender ?? "—")}</td>
      <td>${escapeHtml(r.hidden_segment ?? "—")}</td>
      <td class="preview-cell">${escapeHtml(r.open_ended_preview ?? "")}</td>
      <td><button type="button" class="btn-text analyze-row-btn">▶ RUN</button></td>
    `;
    tr.querySelector(".analyze-row-btn").addEventListener("click", () => {
      analyzeRespondent(r.respondent_id);
    });
    tbody.appendChild(tr);
  });
}

function renderStatResult(rootEl, analysis, respondent, payload) {
  destroyResultNetwork();
  rootEl.innerHTML = "";

  const header = document.createElement("div");
  header.className = "dataset-result-head";
  header.innerHTML = `
    <strong>${escapeHtml(respondent.respondent_id)}</strong>
    <span class="hint"> · ${escapeHtml(respondent.hidden_segment ?? "—")}</span>
  `;
  rootEl.appendChild(header);

  renderComparisonPanel(rootEl, payload);

  const quote = document.createElement("blockquote");
  quote.className = "review-quote";
  quote.textContent = respondent.open_ended_response || "";
  rootEl.appendChild(quote);

  const stats = document.createElement("p");
  stats.className = "meta readout";
  stats.innerHTML = `
    <span class="readout-key">SENTENCES</span> ${analysis.sentence_count}
    <span class="readout-sep">│</span>
    <span class="readout-key">CONCEPTS</span> ${analysis.vocabulary_size}
  `;
  rootEl.appendChild(stats);

  const tabs = document.createElement("div");
  tabs.className = "tabs";
  tabs.setAttribute("role", "tablist");
  TAB_KEYS.forEach((key, i) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = `tab${i === 0 ? " on" : ""}`;
    btn.dataset.tab = key;
    btn.textContent =
      key === "cooccurrence" ? "Co-occurrence" : key === "semantic" ? "Semantic" : "Epistemic";
    tabs.appendChild(btn);
  });
  rootEl.appendChild(tabs);

  const head = document.createElement("div");
  head.className = "output-head";
  const graphStats = document.createElement("span");
  graphStats.className = "hint readout";
  const actions = document.createElement("div");
  actions.className = "output-actions";
  const dlXlsx = document.createElement("button");
  dlXlsx.type = "button";
  dlXlsx.className = "btn-text";
  dlXlsx.textContent = "[ XLSX ]";
  actions.appendChild(dlXlsx);
  head.appendChild(graphStats);
  head.appendChild(actions);
  rootEl.appendChild(head);

  const graphEl = document.createElement("div");
  graphEl.className = "graph review-graph";
  rootEl.appendChild(graphEl);

  const matrixWrap = document.createElement("div");
  matrixWrap.className = "matrix-scroll";
  rootEl.appendChild(matrixWrap);

  let currentTab = "cooccurrence";

  function renderTab(tabKey) {
    currentTab = tabKey;
    rootEl.dataset.accent = tabKey;
    const graph = analysis.graphs?.[tabKey];
    const matrix = analysis.matrices?.[tabKey];

    graphStats.textContent = graph?.stats
      ? `${graph.stats.node_count} nodes · ${graph.stats.edge_count} edges`
      : "";

    networkInstance?.destroy?.();
    networkInstance = mountNetwork(graphEl, graph, tabKey);

    matrixWrap.innerHTML = "";
    if (matrix) matrixWrap.appendChild(buildMatrixTable(matrix, tabKey));
  }

  tabs.querySelectorAll(".tab").forEach((btn) => {
    btn.addEventListener("click", () => {
      tabs.querySelectorAll(".tab").forEach((b) => b.classList.remove("on"));
      btn.classList.add("on");
      renderTab(btn.dataset.tab);
    });
  });

  dlXlsx.addEventListener("click", async () => {
    const m = analysis.matrices?.[currentTab];
    if (!m) return;
    const base = MATRIX_DOWNLOAD_NAMES[currentTab] || "matrix.xlsx";
    try {
      await downloadMatrixXlsx(m, `${respondent.respondent_id}_${base}`);
    } catch (err) {
      showMsg(err.message || String(err), true);
    }
  });

  renderTab(currentTab);
  requestAnimationFrame(() => requestAnimationFrame(() => renderTab(currentTab)));
}

function renderDatasetResult(payload) {
  if (!resultsRoot) return;
  const { respondent, analysis, pipeline } = payload;
  resultsRoot.hidden = false;

  if (pipeline === "fcm" || analysis?.pipeline === "fcm") {
    destroyResultNetwork();
    resultsRoot.innerHTML = "";
    const header = document.createElement("div");
    header.className = "dataset-result-head";
    header.innerHTML = `
      <strong>${escapeHtml(respondent.respondent_id)}</strong>
      <span class="hint"> · FCM · ${escapeHtml(respondent.hidden_segment ?? "—")}</span>
    `;
    resultsRoot.appendChild(header);
    renderComparisonPanel(resultsRoot, payload);
    const quote = document.createElement("blockquote");
    quote.className = "review-quote";
    quote.textContent = respondent.open_ended_response || "";
    resultsRoot.appendChild(quote);
    const body = document.createElement("div");
    body.className = "dataset-fcm-body";
    resultsRoot.appendChild(body);
    renderFcmCard(body, analysis, { reviewIndex: 0 });
    resultsRoot.scrollIntoView({ behavior: "smooth", block: "start" });
    return;
  }

  renderStatResult(resultsRoot, analysis, respondent, payload);
  resultsRoot.scrollIntoView({ behavior: "smooth", block: "start" });
}

async function analyzeRespondent(respondentId) {
  if (analyzing) return;
  showMsg("");
  destroyResultNetwork();
  resultsRoot.hidden = true;
  resultsRoot.innerHTML = "";

  const pipeline = window.getSementicPipeline?.() || "statistical";
  const fd = new FormData();
  fd.append("min_freq", document.getElementById("dataset-min-freq")?.value ?? "0");
  fd.append("pipeline", pipeline);

  const wf = window.sementicWorkflow;
  wf?.reset(stepsForPipeline(pipeline));
  setAnalyzeLoading(true);

  try {
    const res = await fetch(
      `/api/dataset/respondents/${encodeURIComponent(respondentId)}/analyze/stream`,
      { method: "POST", body: fd }
    );
    const data = await consumeNdjsonStream(res, (ev) => wf?.handleEvent(ev));
    renderDatasetResult(data);
  } catch (err) {
    wf?.setStatus("ERROR");
    showMsg(err.message || String(err), true);
  } finally {
    setAnalyzeLoading(false);
  }
}

searchInput?.addEventListener("input", () => {
  clearTimeout(searchTimer);
  const q = searchInput.value.trim();
  searchTimer = setTimeout(() => {
    loadRespondents(q);
    if (fullFold?.open) {
      fullDatasetLoaded = false;
      loadFullDataset(q);
    }
  }, 300);
});

fullFold?.addEventListener("toggle", () => {
  if (fullFold.open && !fullDatasetLoaded) {
    loadFullDataset(searchInput?.value?.trim() || "");
  }
});

async function bootstrap() {
  try {
    const res = await fetch("/api/dataset/config");
    const cfg = await res.json();
    if (!cfg.configured) {
      let msg =
        "Dataset not configured. Place brand_trust_dataset.xlsx in project root or set Google Drive env vars.";
      if (cfg.drive_credentials && cfg.service_account_email) {
        msg = `Drive credentials OK. Share brand_trust_dataset.xlsx with ${cfg.service_account_email} (Viewer), then reload.`;
      }
      showMsg(msg, true);
      return;
    }
    ui.hidden = false;
    await loadRespondents();
  } catch (err) {
    showMsg(err.message || String(err), true);
  }
}

window.addEventListener("sementic:dataset-panel-shown", () => {
  if (!ui.hidden && tbody.children.length === 0) {
    loadRespondents(searchInput?.value?.trim() || "");
  }
});

bootstrap();
