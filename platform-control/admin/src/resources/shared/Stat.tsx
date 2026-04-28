"use client";

import type { CSSProperties } from "react";
import { Panel } from "../../ui/primitives";
import { type AdminStatusLevel, adminLevelBorder } from "./statusLevels";

export type StatTone = "success" | "error" | "warning" | "info" | "default";

function statToneToAdminLevel(tone: StatTone): AdminStatusLevel {
  switch (tone) {
    case "success":
      return "healthy";
    case "error":
      return "critical";
    case "warning":
      return "degraded";
    case "info":
      return "info";
    default:
      return "neutral";
  }
}

/** Top-border accent for dashboard stats/cards — same borders as `StatusBadge` levels. */
export function statToneBorder(tone: StatTone): string {
  return adminLevelBorder(statToneToAdminLevel(tone));
}

/**
 * Derives dashboard card accent for a success-rate string like "85%" or "-".
 * Aligns with design-system plan F2: warn below 95%, critical below 80%.
 */
export function successRateTone(successRate: string): StatTone {
  if (successRate === "-") return "default";
  const n = Number.parseInt(successRate.replace(/%/g, ""), 10);
  if (Number.isNaN(n)) return "default";
  if (n < 80) return "error";
  if (n < 95) return "warning";
  return "success";
}

export function StatCard({
  label,
  value,
  tone = "default",
}: {
  label: string;
  value: string | number;
  tone?: StatTone;
}) {
  return (
    <Panel
      className="min-w-40 flex-1 border-t-4 p-5"
      style={{ borderTopColor: statToneBorder(tone) } as CSSProperties}
    >
      <div className="flex flex-col items-start gap-2">
        <span className="text-[11px] font-semibold uppercase tracking-[0.14em] leading-[1.1] text-[var(--text-meta)]">
          {label}
        </span>
        <strong className="text-[34px] font-bold leading-none text-[var(--foreground)]">
          {value}
        </strong>
        <span className="text-sm leading-snug text-[var(--text-muted)]">At a glance</span>
      </div>
    </Panel>
  );
}
