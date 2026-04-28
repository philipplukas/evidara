/**
 * `Pill` — semantic status badge + neutral metadata chip, zero MUI.
 *
 * `level` aligns with `AdminStatusLevel` (see `resources/shared/StatusBadge.tsx`)
 * so the existing status mapping helpers (`sourceStatusToLevel`,
 * `runRecordStatusToLevel`, …) transfer unchanged. UX-4 pill contract:
 * full-pill radius, 11px text, weight 600, 24px at `size="small"` — matches
 * the MUI chip theme in `AdminApp.tsx` exactly.
 */
"use client";

import {
  AlertTriangle,
  CheckCircle2,
  Info,
  type LucideIcon,
  MinusCircle,
  XCircle,
} from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "./cn";

export type PillLevel = "healthy" | "degraded" | "critical" | "neutral" | "info";

interface LevelStyle {
  Icon: LucideIcon;
  className: string;
}

const LEVELS: Record<PillLevel, LevelStyle> = {
  healthy: {
    Icon: CheckCircle2,
    className:
      "bg-[var(--status-healthy-subtle)] text-[var(--status-healthy)] border-[var(--status-healthy)]/25",
  },
  degraded: {
    Icon: AlertTriangle,
    className:
      "bg-[var(--status-degraded-subtle)] text-[var(--status-degraded)] border-[var(--status-degraded)]/30",
  },
  critical: {
    Icon: XCircle,
    className:
      "bg-[var(--status-critical-subtle)] text-[var(--status-critical)] border-[var(--status-critical)]/30",
  },
  neutral: {
    Icon: MinusCircle,
    className:
      "bg-[var(--status-neutral-subtle)] text-[var(--status-neutral)] border-[var(--status-neutral)]/20",
  },
  info: {
    Icon: Info,
    className:
      "bg-[var(--status-info-subtle)] text-[var(--status-info)] border-[var(--status-info)]/25",
  },
};

interface PillProps {
  level?: PillLevel;
  children: ReactNode;
  /** Render a small neutral "outline" pill without an icon (for metadata like `source_type`). */
  variant?: "status" | "meta";
  className?: string;
}

export function Pill({ level = "neutral", children, variant = "status", className }: PillProps) {
  const { Icon, className: levelClassName } = LEVELS[level];
  const isMeta = variant === "meta";

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full border font-semibold",
        "h-6 px-2 text-[11px] leading-none",
        isMeta
          ? "bg-[var(--surface-panel)] text-[var(--text-meta)] border-[var(--border)]"
          : levelClassName,
        className,
      )}
    >
      {!isMeta ? <Icon size={12} strokeWidth={2.5} aria-hidden /> : null}
      <span>{children}</span>
    </span>
  );
}
