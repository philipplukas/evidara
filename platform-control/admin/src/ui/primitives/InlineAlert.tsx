"use client";

import { AlertTriangle, CheckCircle2, Info, XCircle } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "./cn";

type AlertTone = "info" | "warning" | "error" | "success";

const TONE = {
  info: {
    Icon: Info,
    className:
      "border-[var(--status-info)]/25 bg-[var(--status-info-subtle)] text-[var(--status-info)]",
  },
  warning: {
    Icon: AlertTriangle,
    className:
      "border-[var(--status-degraded)]/30 bg-[var(--status-degraded-subtle)] text-[var(--status-degraded)]",
  },
  error: {
    Icon: XCircle,
    className:
      "border-[var(--status-critical)]/30 bg-[var(--status-critical-subtle)] text-[var(--status-critical)]",
  },
  success: {
    Icon: CheckCircle2,
    className:
      "border-[var(--status-healthy)]/25 bg-[var(--status-healthy-subtle)] text-[var(--status-healthy)]",
  },
} satisfies Record<AlertTone, { Icon: typeof Info; className: string }>;

export function InlineAlert({
  tone = "info",
  children,
  testId,
  className,
}: {
  tone?: AlertTone;
  children: ReactNode;
  testId?: string;
  className?: string;
}) {
  const { Icon, className: toneClassName } = TONE[tone];

  return (
    <div
      data-testid={testId}
      className={cn(
        "flex items-start gap-2 rounded-md border px-4 py-3 text-sm",
        toneClassName,
        className,
      )}
    >
      <Icon size={16} strokeWidth={2.5} className="mt-0.5 shrink-0" aria-hidden />
      <div className="text-[var(--foreground)]">{children}</div>
    </div>
  );
}
