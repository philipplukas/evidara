/**
 * Pure pipeline decision-support / stage-guidance helpers shared by the run
 * detail sections and their tests. Extracted from the retired MUI
 * `RunDetailSections.tsx` during the ADR-0026 cutover.
 */
import type { RunPipelineHealth, RunRecord } from "../../lib/admin/dataProvider";

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

const stageLabel = (stage: RunPipelineHealth["stages"][number]): string =>
  stage.stage.replaceAll("_", " ");

const mostRecentStage = (
  stages: RunPipelineHealth["stages"],
): RunPipelineHealth["stages"][number] | null =>
  stages.reduce<RunPipelineHealth["stages"][number] | null>((latest, stage) => {
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

  const whyItMatters =
    run.mode === "production"
      ? "This production run determines whether the source version can safely flow into the live operator surface."
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

  const blockedStages = health.stages.filter(
    (stage) => stage.status === "blocked" || stage.status === "failed",
  );
  const latestStage = mostRecentStage(health.stages);

  const whatIsBlocked =
    health.overall_status === "ok"
      ? "No stage is blocked right now."
      : blockedStages.length > 0
        ? `Blocked stages: ${blockedStages.map(stageLabel).join(", ")}.`
        : "No stage is blocked, but the pipeline is still moving and may need operator attention soon.";

  const whatChangedRecently = latestStage
    ? `Most recent stage update: ${stageLabel(latestStage)} is ${latestStage.status.replaceAll("_", " ")}.`
    : `Health snapshot recorded ${health.processing_status_event_count} processing events and ${health.document_lifecycle_event_count} lifecycle events.`;

  const whatHappensIfIgnored =
    health.overall_status === "ok"
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

export function stageNextAction(stage: RunPipelineHealth["stages"][number]): string {
  if (stage.status === "ok") return "No action required.";
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

/**
 * Where a blocked stage's remediation CTA points.
 *
 * In-page targets carry a `sectionId` rather than a `#…` href: the admin runs
 * under react-admin's HashRouter, so the URL fragment *is* the route. An
 * `<a href="#di-processing-status-section">` navigates to the (nonexistent)
 * route `/di-processing-status-section` and lands the operator on "page not
 * found". Callers scroll to `sectionId` instead of letting the browser do it.
 */
export type StageActionTarget =
  | { kind: "section"; label: string; sectionId: string }
  | { kind: "external"; label: string; href: string };

export function stageActionTarget(
  stage: RunPipelineHealth["stages"][number],
  options: { legalSearchUrl?: string; evidenceRunbookPath: string },
): StageActionTarget {
  if (stage.stage === "acquisition") {
    return { kind: "section", label: "Jump to provider jobs", sectionId: "provider-jobs-section" };
  }
  if (stage.stage === "document_intelligence") {
    return {
      kind: "section",
      label: "Jump to DI processing",
      sectionId: "di-processing-status-section",
    };
  }
  if (stage.stage === "projection") {
    return {
      kind: "section",
      label: "Jump to document lifecycle",
      sectionId: "document-lifecycle-section",
    };
  }
  if (options.legalSearchUrl) {
    return {
      kind: "external",
      label: "Open legal-search verification",
      href: options.legalSearchUrl,
    };
  }
  return { kind: "external", label: "Open evidence runbook", href: options.evidenceRunbookPath };
}
