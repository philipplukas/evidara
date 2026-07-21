/**
 * `run-decision-support` — the pure, framework-free helpers behind the run
 * detail page: pipeline-stage projection, per-stage next actions, in-page
 * anchor scrolling, and the four-question decision-support copy.
 *
 * They used to live in the v1 MUI `RunDetailSections.tsx` page, which the
 * Tailwind `RunDetailSectionsV2` imported from ("reuses pure helpers from v1")
 * — so the dead v1 page could not be deleted without taking the live one with
 * it. Extracting them here finishes the ADR-0026 collapse for the runs
 * resource (#649): no React, no MUI, no `react-admin`.
 */
import type {
  RunPipelineHealth,
  RunPipelineHealthStage,
  RunRecord,
} from "../../lib/admin/dataProvider";

export const overallSummaryByStatus = (status: RunPipelineHealth["overall_status"]): string => {
  if (status === "ok") return "Pipeline stages are healthy.";
  if (status === "blocked")
    return "One or more stages need remediation before the run can progress.";
  if (status === "failed") return "A downstream stage failed and needs operator attention.";
  return "At least one stage is still moving through the pipeline.";
};

export type PipelineDecisionSupport = {
  whyItMatters: string;
  whatIsBlocked: string;
  whatChangedRecently: string;
  whatHappensIfIgnored: string;
};

/**
 * Stage status *as rendered*. The API only knows the five lifecycle values; the
 * admin adds `not_applicable` for stages that can no longer run (see
 * `projectPipelineStages`).
 */
export type DisplayStageStatus = RunPipelineHealthStage["status"] | "not_applicable";

export type DisplayPipelineStage = Omit<RunPipelineHealthStage, "status"> & {
  status: DisplayStageStatus;
};

const TERMINAL_FAILURE_RUN_STATUSES: readonly string[] = ["failed", "cancelled"];

/**
 * A run that ended as `failed` / `cancelled` will never advance again, so the
 * stages it never reached are dead, not queued.
 */
export function isTerminalFailureRunStatus(status: RunPipelineHealth["run_status"]): boolean {
  return TERMINAL_FAILURE_RUN_STATUSES.includes(status);
}

const notApplicableDetail = (runStatus: RunPipelineHealth["run_status"]): string =>
  runStatus === "cancelled"
    ? "Not applicable — the run was cancelled before this stage could start."
    : "Not applicable — the run failed before this stage could start.";

/**
 * `projectPipelineStages` — render-time projection of the API stage list.
 *
 * On a run that terminally failed (or was cancelled), the API still reports the
 * downstream stages it never reached as `pending`, with copy like "Awaiting DI
 * processing signal before projection stage starts." That reads as "work is
 * still coming" and makes a dead run look like it needs watching. Those stages
 * are re-labelled `not_applicable` instead.
 *
 * Runs that are still progressing (pending / running / completed) are returned
 * untouched — `pending` is genuinely correct there, and a healthy completed run
 * legitimately reports every stage `ok`.
 */
export function projectPipelineStages(health: RunPipelineHealth): DisplayPipelineStage[] {
  if (!isTerminalFailureRunStatus(health.run_status)) {
    return health.stages;
  }
  return health.stages.map((stage) =>
    stage.status === "pending"
      ? { ...stage, status: "not_applicable", detail: notApplicableDetail(health.run_status) }
      : stage,
  );
}

/** A stage needs operator attention only when it is neither healthy nor dead. */
export function stageNeedsAction(status: DisplayStageStatus): boolean {
  return status !== "ok" && status !== "not_applicable";
}

const stageLabel = (stage: DisplayPipelineStage): string => stage.stage.replaceAll("_", " ");

const mostRecentStage = (stages: DisplayPipelineStage[]): DisplayPipelineStage | null =>
  stages.reduce<DisplayPipelineStage | null>((latest, stage) => {
    if (!stage.updated_at) {
      return latest;
    }
    if (!latest?.updated_at) {
      return stage;
    }
    return new Date(stage.updated_at).getTime() > new Date(latest.updated_at).getTime()
      ? stage
      : latest;
  }, null);

export function buildPipelineDecisionSupport(options: {
  run: RunRecord;
  health: RunPipelineHealth | null;
}): PipelineDecisionSupport {
  const { run, health } = options;

  // Three modes, not two. The `production`-vs-everything-else ternary this
  // replaces called an acceptance run "this preview run" — the same mislabelling
  // #743 fixed at the badge sites and missed here, so the page contradicted its
  // own header 400px above.
  const whyItMatters =
    run.mode === "production"
      ? "This production run determines whether the source version can safely flow into the live operator surface."
      : run.mode === "acceptance"
        ? "This acceptance run reaches the live source to produce ADR-0030 evidence. A pass is the justification for enabling the template — it does not by itself turn either key."
        : "This preview run is the gate before promotion, so the result tells operators whether the version is ready.";

  if (!health) {
    return {
      whyItMatters,
      whatIsBlocked: "Pipeline health has not loaded yet, so the blocked state is still unknown.",
      whatChangedRecently:
        "The latest stage movement will appear once the pipeline health snapshot loads.",
      whatHappensIfIgnored:
        "Without an operator check, the run will remain in its current state and no remediation guidance will surface.",
    };
  }

  const stages = projectPipelineStages(health);
  const blockedStages = stages.filter(
    (stage) => stage.status === "blocked" || stage.status === "failed",
  );
  const skippedStages = stages.filter((stage) => stage.status === "not_applicable");
  const latestStage = mostRecentStage(stages);

  const blockedSummary =
    health.overall_status === "ok"
      ? "No stage is blocked right now."
      : blockedStages.length > 0
        ? `Blocked stages: ${blockedStages.map(stageLabel).join(", ")}.`
        : "No stage is blocked, but the pipeline is still moving and may need operator attention soon.";

  const whatIsBlocked =
    skippedStages.length > 0
      ? `${blockedSummary} Downstream stages that will never run: ${skippedStages.map(stageLabel).join(", ")}.`
      : blockedSummary;

  const whatChangedRecently = latestStage
    ? `Most recent stage update: ${stageLabel(latestStage)} is ${latestStage.status.replaceAll("_", " ")}.`
    : `Health snapshot recorded ${health.processing_status_event_count} processing events and ${health.document_lifecycle_event_count} lifecycle events.`;

  const whatHappensIfIgnored = isTerminalFailureRunStatus(health.run_status)
    ? `The run already ended as ${health.run_status}; the stages it never reached will not start on their own, so remediate and relaunch to make progress.`
    : health.overall_status === "ok"
      ? "Nothing urgent happens; the run remains a completed audit trail unless someone investigates it later."
      : health.overall_status === "blocked"
        ? "The run stays blocked until the relevant stage is remediated."
        : health.overall_status === "failed"
          ? "The failure remains unresolved and downstream progress will not clear itself."
          : "The pipeline continues to advance and may still require intervention if a later stage stops.";

  return {
    whyItMatters,
    whatIsBlocked,
    whatChangedRecently,
    whatHappensIfIgnored,
  };
}

export function stageNextAction(stage: DisplayPipelineStage): string {
  if (stage.status === "ok") return "No action required.";
  if (stage.status === "not_applicable") {
    return "No action — this stage will not run for this run.";
  }
  if (stage.stage === "acquisition") {
    return "Check provider jobs for dispatch/crawl status and retry or cancel when stuck.";
  }
  if (stage.stage === "document_intelligence") {
    return "Inspect DI processing status events and error summaries for remediation.";
  }
  if (stage.stage === "projection") {
    return "Confirm document lifecycle events are being emitted for this run.";
  }
  return "Verify lifecycle search disposition and confirm indexed document visibility in legal-search.";
}

export function stageActionTarget(
  stage: DisplayPipelineStage,
  options: { legalSearchUrl?: string; evidenceRunbookPath: string },
): { label: string; href: string } {
  if (stage.stage === "acquisition") {
    return { label: "Jump to provider jobs", href: "#provider-jobs-section" };
  }
  if (stage.stage === "document_intelligence") {
    return { label: "Jump to DI processing", href: "#di-processing-status-section" };
  }
  if (stage.stage === "projection") {
    return { label: "Jump to document lifecycle", href: "#document-lifecycle-section" };
  }
  if (options.legalSearchUrl) {
    return { label: "Open legal-search verification", href: options.legalSearchUrl };
  }
  return { label: "Open evidence runbook", href: options.evidenceRunbookPath };
}

/**
 * `sectionIdFromAnchor` — strip the leading `#` from an in-page anchor href so
 * it can be resolved with `document.getElementById`. Callers pass the raw
 * `stageActionTarget` href (e.g. `#di-processing-status-section`).
 */
export function sectionIdFromAnchor(href: string): string {
  return href.startsWith("#") ? href.slice(1) : href;
}

/**
 * `scrollToInPageSection` — smooth-scroll to the element behind an in-page
 * anchor **without** letting the click reach react-admin's HashRouter.
 *
 * These detail pages render under a `HashRouter`, so a plain `<a href="#foo">`
 * click mutates `location.hash` to `#foo`, which the router parses as a route
 * change and bounces the operator to the "Not Found" page (issue: jump links
 * left the run detail entirely). Resolving the target element and calling
 * `scrollIntoView` ourselves keeps navigation entirely client-side and never
 * touches the hash. No-ops safely if the element is not in the DOM.
 */
export function scrollToInPageSection(href: string): void {
  if (typeof document === "undefined") {
    return;
  }
  const target = document.getElementById(sectionIdFromAnchor(href));
  target?.scrollIntoView({ behavior: "smooth", block: "start" });
}
