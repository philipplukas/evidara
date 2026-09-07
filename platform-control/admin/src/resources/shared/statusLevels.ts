"use client";

export type AdminStatusLevel = "healthy" | "degraded" | "critical" | "neutral" | "info";

const LEVEL_BORDER: Record<AdminStatusLevel, string> = {
  healthy: "color-mix(in srgb, var(--status-healthy) 35%, transparent)",
  degraded: "color-mix(in srgb, var(--status-degraded) 40%, transparent)",
  critical: "color-mix(in srgb, var(--status-critical) 40%, transparent)",
  neutral: "var(--border-strong)",
  info: "color-mix(in srgb, var(--status-info) 35%, transparent)",
};

/** Border color aligned with status pills for cards, rails, and non-chip accents. */
export function adminLevelBorder(level: AdminStatusLevel): string {
  return LEVEL_BORDER[level];
}

/**
 * The run statuses an operator can still do something about.
 *
 * `completed` and `cancelled` are terminal: nothing an operator does advances
 * either, so a screen that nominates one as the thing to look at first has sent
 * them somewhere they cannot act.
 *
 * Lives here, imported by every selector that needs it, because it was defined
 * once in `resources/runs/RunList.tsx` and NOT applied by the dashboard's own
 * selector — which is how the landing page came to lead with a cancelled run
 * while the run queue, on the same data, correctly led with a failed one. That
 * is AGENTS.md's "same rule enforced in two clients": there was only ever one
 * rule, and the copy that did not have it was the one operators saw first.
 */
export const ACTIONABLE_RUN_STATUSES: readonly string[] = ["failed", "running", "pending"];

/** True when a run can still be acted on. See `ACTIONABLE_RUN_STATUSES`. */
export function isActionableRunStatus(status: string | null | undefined): boolean {
  return status != null && ACTIONABLE_RUN_STATUSES.includes(status);
}

export function runRecordStatusToLevel(status: string): AdminStatusLevel {
  switch (status) {
    case "completed":
      return "healthy";
    case "failed":
      return "critical";
    case "running":
      return "info";
    case "pending":
      return "degraded";
    default:
      return "neutral";
  }
}

export function runModeToLevel(mode: string): AdminStatusLevel {
  if (mode === "production") {
    return "healthy";
  }
  // An acceptance run reaches a live portal on a provider with no accepted
  // evidence. Rendering it with the same calm tone as a preview understates what
  // it touches (#743).
  if (mode === "acceptance") {
    return "degraded";
  }
  return "info";
}

export function pipelineHealthToLevel(status: string): AdminStatusLevel {
  switch (status) {
    case "ok":
      return "healthy";
    case "blocked":
      return "degraded";
    case "failed":
      return "critical";
    case "in_progress":
      return "info";
    // Stages the admin marked dead on a terminally-failed run — see
    // `projectPipelineStages`. Neutral, not degraded: nothing is wrong with the
    // stage itself, it simply will never run.
    case "not_applicable":
      return "neutral";
    default:
      return "neutral";
  }
}

export function sourceVersionStatusToLevel(status: string): AdminStatusLevel {
  switch (status) {
    case "approved":
      return "healthy";
    case "pending_approval":
      return "info";
    case "draft":
      return "neutral";
    case "rejected":
      return "critical";
    case "superseded":
      return "neutral";
    default:
      return "neutral";
  }
}

export function sourceStatusToLevel(status: string): AdminStatusLevel {
  switch (status) {
    case "active":
      return "healthy";
    case "inactive":
      return "degraded";
    case "archived":
      return "neutral";
    default:
      return "neutral";
  }
}
