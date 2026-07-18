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
  return mode === "production" ? "healthy" : "info";
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
