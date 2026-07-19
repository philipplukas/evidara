/**
 * Turn `/v1/runs/readiness` into the two launch buttons the source detail page
 * renders — pure, so the decision table is testable without a DOM or a network.
 *
 * Why this exists (#667): `SourceVersionsSection` derived `canPreview` /
 * `canProduction` from the version's **status alone**. The page therefore
 * announced "Ready for preview or production runs" and "No attention needed"
 * over a version whose blueprint template was inert, left both buttons enabled,
 * and handed the operator a 400 from `POST /v1/runs`. The platform's own
 * pre-flight knew: `/v1/runs/readiness` returned `ready: false` with
 * `acquisition_lock_open: false` for that exact version. One launch path
 * (`RunLaunchDialog`) consulted it; the one an operator actually reaches from a
 * freshly created source did not.
 *
 * A single `mode=production` probe answers for both buttons. The ADR-0030 lock,
 * seed presence, and existence checks are mode-independent — only
 * `mode_compatible_with_version_status` distinguishes preview from production —
 * so mode-dependent failures are split out rather than blocking preview too.
 */

import type { RunReadiness, SourceVersionRecord } from "../../lib/admin/dataProvider";
import {
  describeReadinessDetail,
  MODE_DEPENDENT_READINESS_CODES,
} from "../../lib/admin/readiness-messages";

export type LaunchGuard = {
  allowed: boolean;
  /** Operator-facing explanation. `null` only when `allowed` and nothing to warn about. */
  reason: string | null;
};

export type VersionLaunchGuards = {
  /**
   * `checked`   — readiness answered; the guards reflect it.
   * `checking`  — probe in flight; buttons stay disabled rather than promising.
   * `unknown`   — the probe failed. Buttons are NOT force-disabled (a transient
   *               network blip must not lock an operator out of a legitimate
   *               run) but every label says the check did not complete.
   */
  state: "checked" | "checking" | "unknown";
  preview: LaunchGuard;
  production: LaunchGuard;
  /** One line for the row / rollup, or `null` when there is nothing to say. */
  summary: string | null;
};

type VersionStatus = SourceVersionRecord["status"];

const statusAllowsPreview = (status: VersionStatus): boolean =>
  status !== "rejected" && status !== "superseded";

const statusAllowsProduction = (status: VersionStatus): boolean => status === "approved";

const statusReason = (status: VersionStatus): string =>
  status === "rejected"
    ? "Rejected versions cannot launch runs."
    : status === "superseded"
      ? "Superseded versions are read-only."
      : "Only approved versions can launch production runs.";

export const deriveVersionLaunchGuards = ({
  status,
  readiness,
  readinessError,
}: {
  status: VersionStatus;
  readiness: RunReadiness | null;
  readinessError: string | null;
}): VersionLaunchGuards => {
  const previewByStatus = statusAllowsPreview(status);
  const productionByStatus = statusAllowsProduction(status);

  // The probe failed. Say so; do not convert "I don't know" into either a green
  // light or a hard block.
  if (readinessError) {
    const warning = `Readiness could not be checked (${readinessError}). A launch may still be refused.`;
    return {
      state: "unknown",
      preview: {
        allowed: previewByStatus,
        reason: previewByStatus ? warning : statusReason(status),
      },
      production: {
        allowed: productionByStatus,
        reason: productionByStatus ? warning : statusReason(status),
      },
      summary: warning,
    };
  }

  if (!readiness) {
    return {
      state: "checking",
      preview: { allowed: false, reason: "Checking run readiness…" },
      production: { allowed: false, reason: "Checking run readiness…" },
      summary: "Checking run readiness…",
    };
  }

  const failing = readiness.checks.filter((check) => !check.ok);
  const hardBlocks = failing.filter((check) => !MODE_DEPENDENT_READINESS_CODES.has(check.code));

  const describeBlock = (code: string): string => {
    const detail = describeReadinessDetail(code);
    return `${detail.title}. ${detail.action}`;
  };

  if (hardBlocks.length > 0) {
    const reason = describeBlock(hardBlocks[0].code);
    return {
      state: "checked",
      preview: { allowed: false, reason },
      production: { allowed: false, reason },
      summary: reason,
    };
  }

  return {
    state: "checked",
    preview: {
      allowed: previewByStatus,
      reason: previewByStatus ? null : statusReason(status),
    },
    production: {
      allowed: productionByStatus,
      reason: productionByStatus ? null : statusReason(status),
    },
    summary: null,
  };
};

/**
 * Roll the per-version guards up into the one sentence the versions panel shows
 * above the table, replacing the unconditional "Approved versions are ready for
 * operator use and run creation."
 *
 * Returns `null` when the default lifecycle copy is accurate, so the caller
 * keeps its existing text rather than this module owning every string.
 */
export const describeLaunchBlockRollup = (
  guards: VersionLaunchGuards[],
): { tone: "warning" | "info"; headline: string; detail: string } | null => {
  if (guards.length === 0) return null;

  if (guards.some((guard) => guard.state === "checking")) {
    return {
      tone: "info",
      headline: "Checking whether these versions can actually launch…",
      detail: "Run readiness is being verified against the platform's own pre-flight.",
    };
  }

  const unknown = guards.filter((guard) => guard.state === "unknown").length;
  const blocked = guards.filter(
    (guard) => guard.state === "checked" && !guard.preview.allowed && !guard.production.allowed,
  );

  if (blocked.length > 0) {
    return {
      tone: "warning",
      headline: `${blocked.length} version${blocked.length === 1 ? "" : "s"} cannot launch a run right now.`,
      detail: blocked[0].summary ?? "Run readiness reported a blocking check.",
    };
  }

  if (unknown > 0) {
    return {
      tone: "warning",
      headline: "Launch readiness is unknown for at least one version.",
      detail:
        "The readiness pre-flight did not answer, so this page cannot confirm a run would be accepted.",
    };
  }

  return null;
};
