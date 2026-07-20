/**
 * `RunShow` shared helpers — after the v1→v2 runs consolidation (#520) the MUI
 * `<Show>` page component was retired; the canonical run detail page is
 * `RunShowV2` wired through the `runs` resource. This module retains only the
 * pure, framework-free helpers that `RunShowV2` (and the decision-support /
 * handoff unit tests) still consume.
 */
import type { RunRecord } from "../../lib/admin/dataProvider";
import {
  describeLegalSearchHandoff,
  type LegalSearchHandoff,
} from "../../lib/admin/navigationContext";

export type RunDecisionSupport = {
  whyItMatters: string;
  whatIsBlocked: string;
  whatChangedRecently: string;
  whatHappensIfIgnored: string;
};

export type RunHandoffGuidance = {
  whyYouAreHere: string;
  whatToCheckNext: string;
};

const describeRunNextStep = (run: RunRecord): string => {
  if (run.status === "failed") {
    return "Open the pipeline sections below and use the failure reason to pinpoint the blocked stage.";
  }
  if (run.status === "running") {
    return "The run is active. Watch the pipeline health and stage sections for the next operator cue.";
  }
  if (run.status === "pending") {
    return "The run is queued. Review readiness and wait for the first stage update.";
  }
  if (run.status === "completed") {
    return "The run completed successfully. Use the lifecycle sections as the audit trail.";
  }
  return "The run was cancelled. Review the detail sections if the stop was unexpected.";
};

export function buildRunDecisionSupport(run: RunRecord): RunDecisionSupport {
  const whyItMatters =
    run.mode === "production"
      ? "This production run reflects the live path for the source version and should be treated as operator-critical."
      : "This preview run is the checkpoint before promotion, so its outcome decides whether the version is ready.";

  const whatIsBlocked =
    run.status === "failed"
      ? run.failure_reason
        ? `The run is blocked by a recorded failure: ${run.failure_reason}`
        : "The run failed and is blocked until the failing stage is remediated."
      : run.status === "running"
        ? "No stage is blocked yet, but the active pipeline may stop if an upstream stage fails."
        : run.status === "pending"
          ? "Nothing is blocked yet because the run has not started."
          : run.status === "cancelled"
            ? "The run was stopped, so there is no remaining blocked stage to clear."
            : "No blocker is visible from the run record.";

  const whatChangedRecently =
    run.status === "completed"
      ? `The run finalized ${run.captured_resources_count} captured resources and ${run.artifacts_count} artifacts.`
      : run.status === "running"
        ? "The pipeline is still changing, so the stage sections below are the best source of the latest movement."
        : run.status === "pending"
          ? "The run is still waiting in queue, so no stage work has started yet."
          : run.status === "failed"
            ? "The latest recorded change is the failure outcome that operators need to inspect."
            : "No new stage activity is expected after cancellation.";

  const whatHappensIfIgnored =
    run.status === "pending"
      ? "It stays queued until the platform starts it or an operator cancels it."
      : run.status === "running"
        ? "It keeps progressing and may complete or fail without intervention."
        : run.status === "failed"
          ? "It remains failed and the blocked stage will not clear on its own."
          : run.status === "completed"
            ? "It stays as a stable audit trail unless the outcome needs review."
            : "No further pipeline work will happen for this run.";

  return {
    whyItMatters,
    whatIsBlocked,
    whatChangedRecently,
    whatHappensIfIgnored,
  };
}

export function buildRunHandoffGuidance(
  run: RunRecord,
  handoff: LegalSearchHandoff,
): RunHandoffGuidance | null {
  if (!handoff.hasOrigin) {
    return null;
  }

  const contextSummary = describeLegalSearchHandoff(handoff);
  const whyYouAreHere = `You came from legal search. ${contextSummary}.`;
  const whatToCheckNext = `${describeRunNextStep(run)} ${
    handoff.selectedId
      ? `Use the selected item (${handoff.selectedId}) to confirm the source/version pair above is the one you expected.`
      : "Use the source and version IDs above to confirm the run matches the result you were investigating."
  }`;

  return {
    whyYouAreHere,
    whatToCheckNext,
  };
}
