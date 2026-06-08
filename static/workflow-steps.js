/** Mirror of workflow.py step definitions for the browser. */

export const ANALYSIS_STEPS = [
  { id: "normalize", num: "01", label: "NORMALIZE & SPLIT" },
  { id: "translate", num: "02", label: "TRANSLATE → EN" },
  { id: "concepts", num: "03", label: "CONCEPT EXTRACTION" },
  { id: "vocabulary", num: "04", label: "VOCABULARY FILTER" },
  { id: "matrices", num: "05", label: "STAT MATRICES ×3" },
  { id: "graphs", num: "06", label: "BASE GRAPH BUILD" },
  { id: "relations_co", num: "07", label: "AI RELATIONS · CO" },
  { id: "relations_se", num: "08", label: "AI RELATIONS · SE" },
  { id: "relations_ep", num: "09", label: "AI RELATIONS · EP" },
  { id: "sign_matrices", num: "10", label: "SIGNED MATRIX OUT" },
  { id: "complete", num: "11", label: "PIPELINE COMPLETE" },
];

export const FCM_STEPS = [
  { id: "normalize", num: "01", label: "NORMALIZE & SPLIT" },
  { id: "lang_detect", num: "02", label: "LANG DETECT" },
  { id: "translate", num: "03", label: "TRANSLATE (skip if EN)" },
  { id: "phrase_extract", num: "04", label: "THEMATIC CATEGORIES" },
  { id: "phrase_cluster", num: "05", label: "CATEGORY CONSOLIDATE" },
  { id: "concept_merge", num: "06", label: "CONCEPT CODEBOOK" },
  { id: "polarity_context", num: "07", label: "POLARITY CONTEXT" },
  { id: "fcm_edges", num: "08", label: "FCM EDGE INFERENCE" },
  { id: "adjacency_matrix", num: "09", label: "ADJACENCY MATRIX" },
  { id: "graph_render", num: "10", label: "GRAPH RENDER" },
  { id: "complete", num: "11", label: "PIPELINE COMPLETE" },
];

export const PLACES_EXTRA_STEPS = [
  { id: "place_fetch", num: "P1", label: "FETCH REVIEWS" },
  { id: "batch_dispatch", num: "P2", label: "BATCH DISPATCH" },
  { id: "batch_complete", num: "P3", label: "BATCH COMPLETE" },
];

export const PLACES_BATCH_STEPS = [
  ...PLACES_EXTRA_STEPS.slice(0, 2),
  ...ANALYSIS_STEPS,
  PLACES_EXTRA_STEPS[2],
];

export const PLACES_FCM_BATCH_STEPS = [
  ...PLACES_EXTRA_STEPS.slice(0, 2),
  ...FCM_STEPS,
  PLACES_EXTRA_STEPS[2],
];

export function stepsForPipeline(pipeline) {
  return pipeline === "fcm" ? FCM_STEPS : ANALYSIS_STEPS;
}

export function placesBatchStepsForPipeline(pipeline) {
  return pipeline === "fcm" ? PLACES_FCM_BATCH_STEPS : PLACES_BATCH_STEPS;
}
