/**
 * Lab pipeline workflow trace — step list + event log.
 */

import {
  ANALYSIS_STEPS,
  FCM_STEPS,
  PLACES_EXTRA_STEPS,
} from "./workflow-steps.js";

const STEP_MAP = new Map(
  [...ANALYSIS_STEPS, ...FCM_STEPS, ...PLACES_EXTRA_STEPS].map((s) => [s.id, s])
);

function ts() {
  return new Date().toLocaleTimeString("en-GB", { hour12: false });
}

function formatDetail(detail) {
  if (!detail || !Object.keys(detail).length) return "";
  const parts = [];
  if (detail.review_index != null) parts.push(`rev ${detail.review_index + 1}`);
  if (detail.sentences != null) parts.push(`${detail.sentences} sent`);
  if (detail.batch != null) parts.push(`batch ${detail.batch}/${detail.batches}`);
  if (detail.vocabulary_size != null) parts.push(`vocab ${detail.vocabulary_size}`);
  if (detail.concepts != null) parts.push(`${detail.concepts} concepts`);
  if (detail.edges != null) parts.push(`${detail.edges} edges`);
  if (detail.pairs != null) parts.push(`${detail.pairs} pairs`);
  if (detail.reviews != null) parts.push(`${detail.reviews} reviews`);
  if (detail.reason) parts.push(detail.reason);
  return parts.length ? ` · ${parts.join(" · ")}` : "";
}

export function createWorkflowTracker(rootEl) {
  if (!rootEl) return null;

  const stepsEl = rootEl.querySelector("#workflow-steps");
  const logEl = rootEl.querySelector("#workflow-log");
  const statusEl = rootEl.querySelector("#workflow-status");

  const state = new Map();

  function renderSteps(stepDefs) {
    if (!stepsEl) return;
    stepsEl.innerHTML = "";
    state.clear();
    stepDefs.forEach((def) => {
      state.set(def.id, "pending");
      const li = document.createElement("li");
      li.className = "wf-step pending";
      li.dataset.step = def.id;
      li.innerHTML = `
        <span class="wf-num">${def.num}</span>
        <span class="wf-label">${def.label}</span>
        <span class="wf-state" aria-hidden="true">○</span>
      `;
      stepsEl.appendChild(li);
    });
  }

  function setStatus(text) {
    if (statusEl) statusEl.textContent = text || "IDLE";
  }

  function appendLog(stepId, status, detail) {
    if (!logEl) return;
    const def = STEP_MAP.get(stepId);
    const label = def?.label || stepId;
    const line = document.createElement("div");
    line.className = `wf-log-line wf-log-${status}`;
    line.textContent = `${ts()} › ${label} › ${status.toUpperCase()}${formatDetail(detail)}`;
    logEl.appendChild(line);
    logEl.scrollTop = logEl.scrollHeight;
  }

  function updateStep(stepId, status, detail = {}) {
    state.set(stepId, status);
    const li = stepsEl?.querySelector(`[data-step="${stepId}"]`);
    if (li) {
      li.className = `wf-step ${status}`;
      const icon = li.querySelector(".wf-state");
      if (icon) {
        icon.textContent =
          status === "running" ? "◉" : status === "done" ? "●" : status === "error" ? "✕" : "○";
      }
    }
    appendLog(stepId, status, detail);

    if (detail.review_index != null && status === "running") {
      setStatus(`EXEC · REV ${detail.review_index + 1}`);
    } else if (stepId === "complete" && status === "done") {
      setStatus("COMPLETE");
    } else if (stepId === "batch_complete" && status === "done") {
      setStatus("BATCH COMPLETE");
    } else if (status === "running") {
      const def = STEP_MAP.get(stepId);
      setStatus(def ? `EXEC · ${def.num}` : "EXEC");
    }
  }

  function reset(stepDefs = ANALYSIS_STEPS) {
    renderSteps(stepDefs);
    if (logEl) logEl.innerHTML = "";
    setStatus("ARMED");
    rootEl.hidden = false;
    window.dispatchEvent(new CustomEvent("sementic:layout-changed"));
  }

  function hide() {
    rootEl.hidden = true;
  }

  function handleEvent(ev) {
    if (ev?.type !== "progress") return;
    updateStep(ev.step, ev.status, ev.detail || {});
  }

  return { reset, hide, updateStep, handleEvent, setStatus };
}

export { ANALYSIS_STEPS, PLACES_EXTRA_STEPS };
