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
  /** Render a small neutral "outline" pill without an icon (for metadata like `source_type`). */
  variant?: "status" | "meta";
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

  return <StatusBadge status={level} label={pillLabel(children)} className={className} />;
}
