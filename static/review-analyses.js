/**
 * Render per-review Sementic analysis cards (Places → analyze all reviews).
 */

import {
  TAB_KEYS,
  MATRIX_DOWNLOAD_NAMES,
  escapeHtml,
  buildMatrixTable,
  mountNetwork,
  downloadMatrixXlsx,
} from "./analysis-shared.js";

const networkByCard = new Map();

function destroyCardNetworks() {
  networkByCard.forEach((net) => net?.destroy?.());
  networkByCard.clear();
}

function renderCardAnalysis(cardEl, analysis, reviewIndex) {
  const activeTab = "cooccurrence";
  cardEl.dataset.accent = activeTab;

  const stats = document.createElement("p");
  stats.className = "meta";
  stats.textContent = `${analysis.sentence_count} sentences · ${analysis.vocabulary_size} concepts`;
  cardEl.appendChild(stats);

  const conceptsFold = document.createElement("details");
  conceptsFold.className = "fold";
  conceptsFold.innerHTML = "<summary>Concepts</summary>";
  const eng = document.createElement("div");
  eng.className = "concept-lines muted-lines";
  (analysis.english_sentences || []).forEach((line, i) => {
    const p = document.createElement("p");
    p.textContent = `${i + 1}. ${line || "—"}`;
    eng.appendChild(p);
  });
  conceptsFold.appendChild(eng);
  const codes = document.createElement("div");
  codes.className = "concept-lines";
  (analysis.concepts_by_sentence || []).forEach((words, i) => {
    const p = document.createElement("p");
    p.textContent = `${i + 1}. ${words.join(", ") || "—"}`;
    codes.appendChild(p);
  });
  conceptsFold.appendChild(codes);
  cardEl.appendChild(conceptsFold);

  const tabs = document.createElement("div");
  tabs.className = "tabs";
  tabs.setAttribute("role", "tablist");
  TAB_KEYS.forEach((key, i) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = `tab${i === 0 ? " on" : ""}`;
    btn.dataset.tab = key;
    btn.textContent = key === "cooccurrence" ? "Co-occurrence" : key === "semantic" ? "Semantic" : "Epistemic";
    tabs.appendChild(btn);
  });
  cardEl.appendChild(tabs);

  const graphStats = document.createElement("span");
  graphStats.className = "hint graph-stats-line";

  const actions = document.createElement("div");
  actions.className = "output-actions";
  const dlXlsx = document.createElement("button");
  dlXlsx.type = "button";
  dlXlsx.className = "btn-text";
  dlXlsx.textContent = "Download XLSX";
  actions.appendChild(dlXlsx);

  const head = document.createElement("div");
  head.className = "output-head";
  head.appendChild(graphStats);
  head.appendChild(actions);
  cardEl.appendChild(head);

  const graphEl = document.createElement("div");
  graphEl.className = "graph review-graph";
  cardEl.appendChild(graphEl);

  const matrixWrap = document.createElement("div");
  matrixWrap.className = "matrix-scroll";
  cardEl.appendChild(matrixWrap);

  let currentTab = activeTab;

  function renderTab(tabKey) {
    currentTab = tabKey;
    cardEl.dataset.accent = tabKey;
    const graph = analysis.graphs?.[tabKey];
    const matrix = analysis.matrices?.[tabKey];

    if (graph?.stats) {
      graphStats.textContent = `${graph.stats.node_count} nodes · ${graph.stats.edge_count} edges`;
    } else {
      graphStats.textContent = "";
    }

    const prev = networkByCard.get(reviewIndex);
    if (prev) prev.destroy();
    const net = mountNetwork(graphEl, graph, tabKey);
    networkByCard.set(reviewIndex, net);

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
    const name = `review${reviewIndex + 1}_${base}`;
    try {
      await downloadMatrixXlsx(m, name);
    } catch (err) {
      alert(err.message || String(err));
    }
  });

  renderTab(activeTab);
}

export function renderReviewAnalyses(payload, rootEl) {
  if (!rootEl) return;
  destroyCardNetworks();
  rootEl.innerHTML = "";

  const summary = document.createElement("p");
  summary.className = "hint review-analyses-summary";
  const n = payload.analyzed_count ?? 0;
  const s = payload.skipped_count ?? 0;
  summary.textContent = `Analyzed ${n} review(s)${s ? `, skipped ${s}` : ""}. Google returns at most 5 reviews per place.`;
  rootEl.appendChild(summary);

  (payload.analyses || []).forEach((item) => {
    const details = document.createElement("details");
    details.className = "review-analysis-card block";

    const review = item.review || {};
    const stars = review.rating != null ? `${review.rating}★` : "";
    const author = review.author || "Anonymous";
    const title = `Review ${item.review_index + 1}: ${author}${stars ? ` · ${stars}` : ""}`;

    const summaryEl = document.createElement("summary");
    summaryEl.textContent = title;
    details.appendChild(summaryEl);

    const body = document.createElement("div");
    body.className = "review-analysis-body";

    if (review.text) {
      const quote = document.createElement("blockquote");
      quote.className = "review-quote";
      quote.textContent = review.text;
      body.appendChild(quote);
    }

    if (item.skipped) {
      const skip = document.createElement("p");
      skip.className = "error";
      skip.textContent = item.reason || "Skipped";
      body.appendChild(skip);
    } else if (item.error) {
      const err = document.createElement("p");
      err.className = "error";
      err.textContent = item.error;
      body.appendChild(err);
    } else if (item.analysis) {
      renderCardAnalysis(body, item.analysis, item.review_index);
    }

    details.appendChild(body);
    rootEl.appendChild(details);
  });

  rootEl.hidden = false;
}

export function clearReviewAnalyses(rootEl) {
  destroyCardNetworks();
  if (rootEl) {
    rootEl.innerHTML = "";
    rootEl.hidden = true;
  }
}
