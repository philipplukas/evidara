import type { RunPipelineHealth, RunRecord } from "../../lib/admin/dataProvider";

export type ChecklistState = "pending" | "in_progress" | "blocked" | "ok";

export type ChecklistItem = {
  key: "readiness" | "run_started" | "pipeline_visibility" | "search_verification";
  label: string;
  state: ChecklistState;
  detail: string;
};

export function deriveOperatorChecklist(options: {
  run: RunRecord;
  health: RunPipelineHealth | null;
  readinessConfirmed: boolean;
  readinessBlockedCodes: string[];
  verificationOpened: boolean;
}): ChecklistItem[] {
  const { run, health, readinessConfirmed, readinessBlockedCodes, verificationOpened } = options;

  const readiness: ChecklistItem = {
    key: "readiness",
    label: "Readiness passed",
    state: readinessConfirmed ? "ok" : readinessBlockedCodes.length > 0 ? "blocked" : "pending",
    detail: readinessConfirmed
      ? "Preflight was confirmed before launch."
      : readinessBlockedCodes.length > 0
        ? `Blocked by: ${readinessBlockedCodes.join(", ")}`
        : "Preflight result unavailable for this run context.",
  };

  const runStarted: ChecklistItem = {
    key: "run_started",
    label: "Run started",
    state: run.started_at || run.status !== "pending" ? "ok" : "pending",
    detail: run.started_at
      ? `Started at ${new Date(run.started_at).toISOString()}`
      : run.status === "pending"
        ? "Run is still pending."
        : `Run status is ${run.status}.`,
  };

  const pipelineVisibility: ChecklistItem = {
    key: "pipeline_visibility",
    label: "Pipeline stage progression visible",
    state: !health
      ? "pending"
      : health.overall_status === "ok"
        ? "ok"
        : health.overall_status === "in_progress"
          ? "in_progress"
          : "blocked",
    detail: !health
      ? "Pipeline health has not loaded yet."
      : `Overall pipeline state: ${health.overall_status}.`,
  };

  const searchVerification: ChecklistItem = {
    key: "search_verification",
    label: "Legal-search verification opened",
    state: verificationOpened ? "ok" : "pending",
    detail: verificationOpened
      ? "Operator opened legal-search verification."
      : "Open legal-search verification from this run.",
  };

  return [readiness, runStarted, pipelineVisibility, searchVerification];
}
