/**
 * The pipeline-health payload the run-detail specs mock.
 *
 * Shared rather than pasted into each spec: it was duplicated in
 * `runs-v2-parity` and `preview-review-v2`, and #908 made it grow a required
 * `decision_support` object. Two hand-maintained copies of a payload the app now
 * reads fields out of is a drift waiting to happen — and the failure mode is a spec
 * that mocks a response the API cannot return, which passes while the real page
 * breaks.
 */

/** Every field `RunPipelineHealthResponse.decision_support` requires. */
export const DECISION_SUPPORT = {
  overall_summary: {
    code: "still_moving",
    text: "At least one stage is still moving through the pipeline.",
  },
  why_it_matters: {
    code: "preview_run",
    text: "This preview run is the gate before promotion, so the result tells operators whether the version is ready.",
  },
  what_is_blocked: { code: "no_stage_blocked", text: "No stage is blocked right now." },
  what_changed_recently: {
    code: "no_stage_updates",
    text: "Health snapshot recorded 0 processing events and 0 lifecycle events.",
  },
  what_happens_if_ignored: {
    code: "continues_advancing",
    text: "The pipeline continues to advance and may still require intervention if a later stage stops.",
  },
  blocked_stages: [],
  never_running_stages: [],
  next_actions: [],
};

export const pipelineHealth = (runId: string) => ({
  run_id: runId,
  source_id: "src_1",
  source_version_id: "sv_1",
  mode: "preview",
  run_status: "running",
  overall_status: "in_progress",
  stages: [],
  processing_status_event_count: 0,
  document_lifecycle_event_count: 0,
  decision_support: DECISION_SUPPORT,
});
