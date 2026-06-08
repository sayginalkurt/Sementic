/**
 * CH-D: Audio record / upload → Gemini transcribe → Sementic pipeline.
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
import { audioStepsForPipeline } from "./workflow-steps.js";
import { renderFcmCard, destroyFcmNetworks } from "./fcm-results.js";

const configMsg = document.getElementById("audio-config-msg");
const ui = document.getElementById("audio-ui");
const recordBtn = document.getElementById("audio-record-btn");
const stopBtn = document.getElementById("audio-stop-btn");
const timerEl = document.getElementById("audio-timer");
const fileInput = document.getElementById("audio-file-input");
const fileNameEl = document.getElementById("audio-file-name");
const previewWrap = document.getElementById("audio-preview-wrap");
const previewEl = document.getElementById("audio-preview");
const analyzeBtn = document.getElementById("audio-analyze-btn");
const errorMsg = document.getElementById("audio-error-msg");
const analyzeLoadingEl = document.getElementById("audio-analyze-loading");
const resultsRoot = document.getElementById("audio-results-root");

let mediaRecorder = null;
let recordChunks = [];
let recordTimer = null;
let recordSeconds = 0;
let audioBlob = null;
let audioMime = "audio/webm";
let previewUrl = null;
let networkInstance = null;
let analyzing = false;

function showMsg(text, isError = false) {
  configMsg.hidden = !text;
  configMsg.textContent = text || "";
  configMsg.classList.toggle("error", isError);
}

function showError(text) {
  errorMsg.hidden = !text;
  errorMsg.textContent = text || "";
}

function setAnalyzeLoading(on) {
  analyzeLoadingEl.hidden = !on;
  analyzing = on;
  recordBtn.disabled = on;
  stopBtn.disabled = on || !mediaRecorder || mediaRecorder.state !== "recording";
  fileInput.disabled = on;
  analyzeBtn.disabled = on || !audioBlob;
}

function destroyResultNetwork() {
  networkInstance?.destroy?.();
  networkInstance = null;
  destroyFcmNetworks();
}

function formatTimer(sec) {
  const m = String(Math.floor(sec / 60)).padStart(2, "0");
  const s = String(sec % 60).padStart(2, "0");
  return `${m}:${s}`;
}

function clearPreviewUrl() {
  if (previewUrl) {
    URL.revokeObjectURL(previewUrl);
    previewUrl = null;
  }
}

function setAudioBlob(blob, mimeType, label = "") {
  audioBlob = blob;
  audioMime = mimeType || blob.type || "audio/webm";
  clearPreviewUrl();
  previewUrl = URL.createObjectURL(blob);
  previewEl.src = previewUrl;
  previewWrap.hidden = false;
  fileNameEl.textContent = label || `${(blob.size / 1024).toFixed(1)} KB · ${audioMime}`;
  analyzeBtn.disabled = analyzing || !audioBlob;
  resultsRoot.hidden = true;
  resultsRoot.innerHTML = "";
  destroyResultNetwork();
}

async function initConfig() {
  try {
    const res = await fetch("/api/audio/config");
    const data = await res.json().catch(() => ({}));
    if (!data.configured) {
      showMsg("GEMINI_API_KEY not configured. Add it to .env to enable audio transcription.", true);
      ui.hidden = true;
      return;
    }
    showMsg(`GEMINI OK · model: ${data.model || "gemini-3.5-flash"}`);
    ui.hidden = false;
  } catch (err) {
    showMsg(err.message || String(err), true);
    ui.hidden = true;
  }
}

async function startRecording() {
  showError("");
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    recordChunks = [];
    const preferredMime = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
      ? "audio/webm;codecs=opus"
      : "audio/webm";
    mediaRecorder = new MediaRecorder(stream, { mimeType: preferredMime });
    mediaRecorder.ondataavailable = (ev) => {
      if (ev.data.size > 0) recordChunks.push(ev.data);
    };
    mediaRecorder.onstop = () => {
      stream.getTracks().forEach((t) => t.stop());
      const blob = new Blob(recordChunks, { type: mediaRecorder.mimeType || "audio/webm" });
      const mime = (mediaRecorder.mimeType || "audio/webm").split(";")[0];
      setAudioBlob(blob, mime, `Recording · ${formatTimer(recordSeconds)}`);
      recordBtn.disabled = false;
      stopBtn.disabled = true;
    };
    mediaRecorder.start(250);
    recordSeconds = 0;
    timerEl.textContent = "00:00";
    recordTimer = setInterval(() => {
      recordSeconds += 1;
      timerEl.textContent = formatTimer(recordSeconds);
    }, 1000);
    recordBtn.disabled = true;
    stopBtn.disabled = false;
  } catch (err) {
    showError(err.message || "Microphone access denied.");
  }
}

function stopRecording() {
  if (recordTimer) {
    clearInterval(recordTimer);
    recordTimer = null;
  }
  if (mediaRecorder && mediaRecorder.state === "recording") {
    mediaRecorder.stop();
  }
}

fileInput.addEventListener("change", () => {
  showError("");
  const file = fileInput.files?.[0];
  if (!file) return;
  setAudioBlob(file, file.type || "audio/mpeg", file.name);
});

recordBtn.addEventListener("click", startRecording);
stopBtn.addEventListener("click", stopRecording);

function renderStatResult(rootEl, analysis, payload) {
  destroyResultNetwork();
  rootEl.innerHTML = "";

  const txBlock = document.createElement("details");
  txBlock.className = "fold";
  txBlock.open = true;
  txBlock.innerHTML = `
    <summary>[ EXPAND ] Gemini transcript</summary>
    <p class="hint readout">
      <span class="readout-key">MODEL</span> ${escapeHtml(payload.transcription?.model || "—")}
      <span class="readout-sep">│</span>
      <span class="readout-key">CHARS</span> ${payload.transcription?.chars ?? "—"}
    </p>
    <blockquote class="review-quote">${escapeHtml(payload.transcript || "")}</blockquote>
  `;
  rootEl.appendChild(txBlock);

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
    await downloadMatrixXlsx(m, MATRIX_DOWNLOAD_NAMES[currentTab] || "matrix.xlsx");
  });

  renderTab("cooccurrence");
}

async function runAnalysis() {
  if (!audioBlob) {
    showError("Record or upload audio first.");
    return;
  }

  showError("");
  setAnalyzeLoading(true);
  resultsRoot.hidden = true;
  resultsRoot.innerHTML = "";
  destroyResultNetwork();

  const pipeline = window.getSementicPipeline?.() || "statistical";
  const minFreq = Number(document.getElementById("audio-min-freq")?.value || 0);
  const wf = window.sementicWorkflow;
  const steps = audioStepsForPipeline(pipeline);

  wf?.reset(steps);
  wf?.setStatus("RUNNING");

  const form = new FormData();
  const ext = audioMime.includes("wav")
    ? "wav"
    : audioMime.includes("mpeg") || audioMime.includes("mp3")
      ? "mp3"
      : "webm";
  form.append("audio", audioBlob, `recording.${ext}`);
  form.append("min_freq", String(minFreq));
  form.append("pipeline", pipeline);

  try {
    const res = await fetch("/api/audio/analyze/stream", { method: "POST", body: form });
    const payload = await consumeNdjsonStream(res, (ev) => wf?.handleEvent(ev));

    wf?.setStatus("DONE");
    resultsRoot.hidden = false;

    const analysis = payload.analysis;
    if (pipeline === "fcm") {
      resultsRoot.innerHTML = "";
      const txBlock = document.createElement("details");
      txBlock.className = "fold";
      txBlock.open = true;
      txBlock.innerHTML = `
        <summary>[ EXPAND ] Gemini transcript</summary>
        <p class="hint readout">
          <span class="readout-key">MODEL</span> ${escapeHtml(payload.transcription?.model || "—")}
          <span class="readout-sep">│</span>
          <span class="readout-key">CHARS</span> ${payload.transcription?.chars ?? "—"}
        </p>
        <blockquote class="review-quote">${escapeHtml(payload.transcript || "")}</blockquote>
      `;
      resultsRoot.appendChild(txBlock);
      renderFcmCard(resultsRoot, analysis, { title: "FCM — Audio transcript" });
    } else {
      renderStatResult(resultsRoot, analysis, payload);
    }

    resultsRoot.scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (err) {
    wf?.setStatus("ERROR");
    showError(err.message || String(err));
  } finally {
    setAnalyzeLoading(false);
  }
}

analyzeBtn.addEventListener("click", runAnalysis);

window.addEventListener("sementic:audio-panel-shown", () => {
  initConfig();
});

window.addEventListener("sementic:pipeline-changed", () => {
  const note = document.getElementById("protocol-note-audio");
  const pipeline = window.getSementicPipeline?.() || "statistical";
  if (note) {
    note.textContent =
      pipeline === "fcm"
        ? "PROTOCOL D · FCM — Audio ingest → Gemini transcribe → thematic causal map"
        : "PROTOCOL D · STAT-3NET — Audio ingest → Gemini transcribe → text pipeline → network map";
  }
  document.getElementById("audio-min-freq-wrap")?.classList.toggle("hidden-stat-only", pipeline === "fcm");
});

if (document.getElementById("panel-audio")?.classList.contains("on")) {
  initConfig();
}
