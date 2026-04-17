"use client";

import { AlertTriangle, RotateCcw } from "lucide-react";

/**
 * Next.js route-level error boundary.
 * Shows a centered error card with retry button.
 */
export default function ErrorPage({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="flex items-center justify-center h-screen bg-surface-page">
      <div className="max-w-md mx-auto text-center px-6">
        <div className="w-14 h-14 rounded-full bg-destructive/10 flex items-center justify-center mx-auto mb-4">
          <AlertTriangle className="w-6 h-6 text-destructive" />
        </div>

        <h2 className="text-lg font-semibold text-foreground mb-2">Something went wrong</h2>

        <p className="text-sm text-muted-foreground mb-6">
          {error.message || "An unexpected error occurred while loading the workspace."}
        </p>

        {error.digest && (
          <p className="text-xs text-muted-foreground/60 mb-4 font-mono">
            Error ID: {error.digest}
          </p>
        )}

        <button
          type="button"
          onClick={reset}
          className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-primary text-white text-sm font-medium
            hover:bg-primary/85 transition-colors focus:outline-none focus:ring-2 focus:ring-focus-ring"
        >
          <RotateCcw className="w-4 h-4" />
          Try again
        </button>
      </div>
    </div>
  );
}
