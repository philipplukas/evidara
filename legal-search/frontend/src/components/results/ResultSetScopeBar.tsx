"use client";

import { ChevronLeft } from "lucide-react";
import type { ResultSetSource } from "@/lib/types";
import { useWorkspace } from "@/lib/workspace-store";
import { ActionTextLink } from "../primitives";

function describeScopeTrail(source: ResultSetSource): string {
  if (source.type === "search") {
    return `Search for "${source.query}"`;
  }

  return `${describeScopeTrail(source.parentSource)} · ${source.label}`;
}

export function ResultSetScopeBar() {
  const { state, dispatch } = useWorkspace();
  const canGoBack = state.resultSetStack.length > 0;
  const currentSource = state.resultSet.source;
  const previousScope = canGoBack ? state.resultSetStack[state.resultSetStack.length - 1] : null;

  return (
    <div className="flex flex-col gap-3 border-b border-border/60 bg-surface-page/80 px-4 py-3 sm:flex-row sm:items-start sm:px-5">
      {canGoBack && previousScope && (
        <div className="shrink-0 pt-0.5 sm:max-w-[11rem]">
          <ActionTextLink
            onClick={() => dispatch({ type: "BACK" })}
            className="shrink-0"
            showArrow={false}
          >
            <ChevronLeft className="w-3.5 h-3.5" />
            Back
          </ActionTextLink>
          <p className="mt-1 truncate text-[11px] text-muted-foreground">
            Previous scope: {previousScope.scopeLabel}
          </p>
        </div>
      )}

      <div className="min-w-0 flex-1">
        <div className="mb-1 flex items-center gap-2">
          <span className="inline-flex items-center rounded-full border border-border/70 bg-muted/40 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
            Current scope
          </span>
          <span className="truncate text-[11px] text-muted-foreground/80">
            {currentSource.type === "search" ? "Root search" : "Pivoted scope"}
          </span>
        </div>
        <div className="truncate text-sm font-medium text-foreground">
          {state.resultSet.scopeLabel}
        </div>
        <div className="truncate text-xs text-muted-foreground">
          {describeScopeTrail(currentSource)}
        </div>
      </div>
    </div>
  );
}
