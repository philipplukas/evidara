import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

interface EmptyStateProps {
  /** Lucide icon component rendered inside a circular badge. */
  icon: LucideIcon;
  /** Primary heading. */
  title: string;
  /** Secondary explanatory copy. */
  description?: string;
  /** Optional action area rendered below the description (e.g. example query chips). */
  action?: ReactNode;
  /** Additional wrapper classes. */
  className?: string;
}

/**
 * Reusable empty-state placeholder used across the workspace panels.
 *
 * Follows the existing visual language: muted circular icon badge, small
 * heading, and faint description — consistent with the patterns already
 * established in ResultList and DetailPanel.
 */
export function EmptyState({ icon: Icon, title, description, action, className }: EmptyStateProps) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center py-20 text-center px-6",
        className,
      )}
      role="status"
      aria-live="polite"
    >
      <div className="w-12 h-12 rounded-full bg-muted flex items-center justify-center mb-4" aria-hidden="true">
        <Icon className="w-5 h-5 text-muted-foreground/40" />
      </div>
      <h3 className="mb-1 text-sm font-medium text-foreground">{title}</h3>
      {description && (
        <p className="max-w-xs text-xs text-muted-foreground">{description}</p>
      )}
      {action && <div className="mt-4 max-w-sm">{action}</div>}
    </div>
  );
}
