"use client";

import { AlertCircle, RotateCcw } from "lucide-react";
import { useTranslations } from "next-intl";

interface ErrorStateProps {
  /** Primary message shown to the user. */
  message: string;
  /** Optional secondary description with more context. */
  description?: string;
  /** When provided, a "Try again" button is rendered. */
  onRetry?: () => void;
  /** Label for the retry button. Falls back to the `error.tryAgain` translation key. */
  retryLabel?: string;
  /** Additional CSS class names on the outer wrapper. */
  className?: string;
}

/**
 * Reusable inline error state for component-level failures.
 *
 * Displays an icon, a configurable message, and an optional retry button.
 * Styled with design-system tokens so it fits into any panel.
 */
export function ErrorState({
  message,
  description,
  onRetry,
  retryLabel,
  className,
}: ErrorStateProps) {
  const t = useTranslations("error");
  const resolvedRetryLabel = retryLabel ?? t("tryAgain");
  return (
    <div
      className={`flex flex-col items-center justify-center py-12 text-center ${className ?? ""}`}
      role="alert"
    >
      <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-full bg-destructive/10">
        <AlertCircle className="h-5 w-5 text-destructive" />
      </div>

      <p className="text-sm font-medium text-foreground">{message}</p>

      {description && (
        <p className="mt-1 max-w-xs text-xs text-muted-foreground">{description}</p>
      )}

      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="mt-4 inline-flex items-center gap-1.5 rounded-lg border border-border bg-background px-3 py-1.5 text-xs font-medium text-muted-foreground transition-colors hover:border-accent-core/30 hover:bg-muted/40 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring"
        >
          <RotateCcw className="h-3 w-3" />
          {resolvedRetryLabel}
        </button>
      )}
    </div>
  );
}
