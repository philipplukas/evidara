/**
 * `Pill` — admin-side adapter over the shared `StatusBadge` primitive.
 *
 * The status-variant rendering is delegated to `@evidara/ui`'s `StatusBadge`
 * so the workspace and admin surfaces stay aligned on the ADR-0016 status
 * pill contract (status colour + icon + redundant label, all driven by the
 * shared `--status-*` tokens). The admin-only `meta` variant — a neutral
 * "outline" chip used for non-status metadata such as `source_type` — has
 * no shared equivalent today and is preserved locally so existing
 * `<Pill variant="meta">…</Pill>` callers render unchanged.
 *
 * `PillLevel` is re-exported as an alias for `@evidara/ui`'s `StatusLevel`
 * so admin call sites that import `PillLevel` from `../../ui/primitives`
 * keep compiling.
 */
"use client";

import { StatusBadge, type StatusLevel } from "@evidara/ui";
import type { ReactNode } from "react";
import { cn } from "./cn";

export type PillLevel = StatusLevel;

interface PillProps {
  level?: PillLevel;
  children: ReactNode;
  /**
   * - `status` — the ADR-0016 badge: colour **and** icon, for a lifecycle state.
   * - `meta` — a small neutral outline chip, no colour, no icon (`source_type`).
   * - `tag` — level colour, **no icon**: a classification that carries risk but
   *   is not a status.
   *
   * `tag` exists because the icon vocabulary was doing two jobs at once. In the
   * run queue's STATE column `pending` renders ⚠, `running` ⓘ, `completed` ✓;
   * in the *mode* badge immediately beside it, `acceptance` rendered ⚠,
   * `preview` ⓘ and `production` ✓. Two adjacent columns, one glyph set,
   * contradictory meanings — a ⚠ that means "queued" next to a ⚠ that means
   * "this reaches a live portal".
   *
   * The decision this encodes: **icons mean lifecycle status and nothing else.**
   * Mode keeps its colour, because the colour is load-bearing — #743 chose
   * `degraded` for `acceptance` deliberately, so that a run touching a live
   * portal on an unproven provider does not read as calmly as a preview. Only
   * the glyph goes.
   */
  variant?: "status" | "meta" | "tag";
  className?: string;
}

/**
 * Flatten pill children into the plain `string` the shared `StatusBadge` takes.
 *
 * `String(children)` is wrong the moment a caller writes JSX with more than one
 * child — `<Pill>{status}: {count}</Pill>` hands React the array
 * `["failed", ": ", 1]`, and `String(...)` on an array joins with commas, which
 * rendered as `failed,: ,1` on the dashboard status pills. Join recursively
 * with no separator instead.
 */
export function pillLabel(children: ReactNode): string {
  if (children === null || children === undefined || typeof children === "boolean") {
    return "";
  }
  if (Array.isArray(children)) {
    return children.map((child) => pillLabel(child as ReactNode)).join("");
  }
  return String(children);
}

export function Pill({ level = "neutral", children, variant = "status", className }: PillProps) {
  if (variant === "meta") {
    return (
      <span
        className={cn(
          "inline-flex items-center gap-1 rounded-full border font-semibold",
          "h-6 px-2 text-[11px] leading-none",
          "bg-[var(--surface-panel)] text-[var(--text-meta)] border-[var(--border)]",
          className,
        )}
      >
        <span>{children}</span>
      </span>
    );
  }

  if (variant === "tag") {
    // Same geometry and the same `--status-*` colour ramp as `StatusBadge`, so a
    // tag and a status badge still read as one family — minus the icon, which is
    // the whole point. `border-current/15` matches the shared badge's border.
    return (
      <span
        className={cn(
          "inline-flex items-center rounded-full border font-medium",
          "px-2 py-0.5 text-tiny border-current/15",
          TAG_TONE[level],
          className,
        )}
      >
        {children}
      </span>
    );
  }

  return <StatusBadge status={level} label={pillLabel(children)} className={className} />;
}

/**
 * Colour only. Mirrors `STATUS_TOKEN_MAP`'s `color` + `subtleBg` pairs from
 * `@evidara/ui`; the icon column is deliberately absent.
 */
const TAG_TONE: Record<PillLevel, string> = {
  healthy: "text-status-healthy bg-status-healthy-subtle",
  degraded: "text-status-degraded bg-status-degraded-subtle",
  critical: "text-status-critical bg-status-critical-subtle",
  neutral: "text-status-neutral bg-status-neutral-subtle",
  info: "text-status-info bg-status-info-subtle",
};
