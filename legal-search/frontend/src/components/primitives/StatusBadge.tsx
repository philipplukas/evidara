"use client";

import { STATUS_TOKEN_MAP, type StatusLevel } from "@/lib/status-tokens";
import { cn } from "@/lib/utils";

interface StatusBadgeProps {
  status: StatusLevel;
  label: string;
  size?: "sm" | "md";
  className?: string;
}

export function StatusBadge({ status, label, size = "sm", className }: StatusBadgeProps) {
  const tokens = STATUS_TOKEN_MAP[status];
  const Icon = tokens.icon;

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border font-medium",
        tokens.subtleBg,
        tokens.color,
        size === "sm"
          ? "px-2 py-0.5 text-[10px] border-current/15"
          : "px-2.5 py-1 text-xs border-current/15",
        className,
      )}
    >
      <Icon className={size === "sm" ? "h-3 w-3" : "h-3.5 w-3.5"} />
      {label}
    </span>
  );
}
