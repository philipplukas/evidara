"use client";

import { AlertCircle, FileQuestion, type LucideIcon, RotateCcw, X } from "lucide-react";

type IconKind = "error" | "notFound";
type ActionIcon = "retry" | "close";

interface DetailAction {
  label: string;
  onClick: () => void;
  icon?: ActionIcon;
}

interface DetailUnavailableStateProps {
  role: "alert" | "status";
  icon: IconKind;
  title: string;
  description?: string;
  primaryAction: DetailAction;
  secondaryAction?: DetailAction;
}

const ICONS: Record<IconKind, { Icon: LucideIcon; tint: string; bg: string }> = {
  error: {
    Icon: AlertCircle,
    tint: "text-destructive",
    bg: "bg-destructive/10",
  },
  notFound: {
    Icon: FileQuestion,
    tint: "text-muted-foreground",
    bg: "bg-muted",
  },
};

const ACTION_ICONS: Record<ActionIcon, LucideIcon> = {
  retry: RotateCcw,
  close: X,
};

export function DetailUnavailableState({
  role,
  icon,
  title,
  description,
  primaryAction,
  secondaryAction,
}: DetailUnavailableStateProps) {
  const { Icon, tint, bg } = ICONS[icon];
  return (
    <div
      role={role}
      aria-live={role === "status" ? "polite" : "assertive"}
      className="flex h-full flex-col items-center justify-center px-6 py-12 text-center"
    >
      <div className={`mb-3 flex h-10 w-10 items-center justify-center rounded-full ${bg}`}>
        <Icon className={`h-5 w-5 ${tint}`} />
      </div>
      <p className="text-sm font-medium text-foreground">{title}</p>
      {description && <p className="mt-1 max-w-xs text-xs text-muted-foreground">{description}</p>}
      <div className="mt-4 flex items-center gap-2">
        <DetailActionButton action={primaryAction} variant="primary" />
        {secondaryAction && <DetailActionButton action={secondaryAction} variant="secondary" />}
      </div>
    </div>
  );
}

function DetailActionButton({
  action,
  variant,
}: {
  action: DetailAction;
  variant: "primary" | "secondary";
}) {
  const ActionIcon = action.icon ? ACTION_ICONS[action.icon] : null;
  const base =
    "inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring";
  const style =
    variant === "primary"
      ? "border border-border bg-background text-foreground hover:border-accent-core/30 hover:bg-muted/40"
      : "text-muted-foreground hover:text-foreground";
  return (
    <button type="button" onClick={action.onClick} className={`${base} ${style}`}>
      {ActionIcon && <ActionIcon className="h-3 w-3" />}
      {action.label}
    </button>
  );
}
