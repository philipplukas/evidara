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
    className: "bg-[rgba(46,125,50,0.08)] text-[#1b5e20] border-[rgba(46,125,50,0.35)]",
  },
  degraded: {
    Icon: AlertTriangle,
    className: "bg-[rgba(237,108,2,0.1)] text-[#e65100] border-[rgba(237,108,2,0.4)]",
  },
  critical: {
    Icon: XCircle,
    className: "bg-[rgba(198,40,40,0.08)] text-[#b71c1c] border-[rgba(198,40,40,0.4)]",
  },
  neutral: {
    Icon: MinusCircle,
    className: "bg-[rgba(29,41,61,0.06)] text-[rgba(29,41,61,0.75)] border-[rgba(29,41,61,0.2)]",
  },
  info: {
    Icon: Info,
    className: "bg-[rgba(2,136,209,0.08)] text-[#01579b] border-[rgba(2,136,209,0.35)]",
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
          ? "bg-white/60 text-[rgba(29,41,61,0.7)] border-[rgba(29,41,61,0.16)]"
          : levelClassName,
        className,
      )}
    >
      {!isMeta ? <Icon size={12} strokeWidth={2.5} aria-hidden /> : null}
      <span>{children}</span>
    </span>
  );
}
