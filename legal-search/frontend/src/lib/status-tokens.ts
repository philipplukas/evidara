import { AlertTriangle, CheckCircle, Info, MinusCircle, XCircle } from "lucide-react";
import type { ComponentType } from "react";

export type StatusLevel = "healthy" | "degraded" | "critical" | "neutral" | "info";

export interface StatusTokens {
  color: string;
  subtleBg: string;
  icon: ComponentType<{ className?: string }>;
  defaultLabel: string;
}

export const STATUS_TOKEN_MAP: Record<StatusLevel, StatusTokens> = {
  healthy: {
    color: "text-status-healthy",
    subtleBg: "bg-status-healthy-subtle",
    icon: CheckCircle,
    defaultLabel: "Healthy",
  },
  degraded: {
    color: "text-status-degraded",
    subtleBg: "bg-status-degraded-subtle",
    icon: AlertTriangle,
    defaultLabel: "Degraded",
  },
  critical: {
    color: "text-status-critical",
    subtleBg: "bg-status-critical-subtle",
    icon: XCircle,
    defaultLabel: "Critical",
  },
  neutral: {
    color: "text-status-neutral",
    subtleBg: "bg-status-neutral-subtle",
    icon: MinusCircle,
    defaultLabel: "Neutral",
  },
  info: {
    color: "text-status-info",
    subtleBg: "bg-status-info-subtle",
    icon: Info,
    defaultLabel: "Info",
  },
};
