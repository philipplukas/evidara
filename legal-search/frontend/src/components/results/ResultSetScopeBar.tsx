"use client";

import { ChevronLeft } from "lucide-react";
import { useTranslations } from "next-intl";
import type { ResultSetSource } from "@/lib/types";
import { useWorkspace } from "@/lib/workspace-store";

function describeScopeTrail(
  source: ResultSetSource,
  searchForFn: (query: string) => string,
): string {
  if (source.type === "search") {
    return searchForFn(source.query);
  }

  return `${describeScopeTrail(source.parentSource, searchForFn)} · ${source.label}`;
}

export function ResultSetScopeBar() {
  const t = useTranslations("results.scope");
  const { state, dispatch } = useWorkspace();
  const canGoBack = state.resultSetStack.length > 0;
  const currentSource = state.resultSet.source;
  const sourceKindLabel = currentSource.type === "search" ? t("rootSearch") : t("refinedScope");

  return (
    <div className="flex items-center gap-2 border-b border-border/60 px-4 py-2.5 sm:px-5">
      {canGoBack && (
        <button
          type="button"
          onClick={() => dispatch({ type: "BACK" })}
          className="inline-flex shrink-0 items-center gap-1 rounded-lg border border-border/70 bg-surface-panel px-2.5 py-1.5 text-xs font-medium text-muted-foreground transition-colors hover:border-accent-core/30 hover:text-foreground"
        >
          <ChevronLeft className="h-3.5 w-3.5" />
          {t("back")}
        </button>
      )}
      <div className="flex min-w-0 flex-1 items-center gap-2">
        <span className="inline-flex shrink-0 items-center rounded-full border border-border/70 bg-muted/45 px-2 py-0.5 text-tiny font-semibold uppercase tracking-[0.16em] text-text-meta">
          {sourceKindLabel}
        </span>
        <span className="truncate text-sm font-semibold text-foreground">
          {state.resultSet.scopeLabel}
        </span>
      </div>
      {currentSource.type === "pivot" && (
        <span className="hidden text-micro text-text-meta sm:block">
          {describeScopeTrail(currentSource, (q) => t("searchFor", { query: q }))}
        </span>
      )}
    </div>
  );
}
