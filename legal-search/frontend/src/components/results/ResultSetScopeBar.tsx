"use client";

import { ChevronLeft } from "lucide-react";
import { useTranslations } from "next-intl";
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
  const t = useTranslations("results.scope");
  const { state, dispatch } = useWorkspace();
  const canGoBack = state.resultSetStack.length > 0;
  const currentSource = state.resultSet.source;
  const previousScope = canGoBack ? state.resultSetStack[state.resultSetStack.length - 1] : null;
  const sourceKindLabel = currentSource.type === "search" ? t("rootSearch") : t("refinedScope");

  return (
    <div className="flex flex-col gap-3 px-4 py-3.5 sm:flex-row sm:items-start sm:gap-4 sm:px-5">
      {canGoBack && previousScope && (
        <div className="shrink-0 rounded-2xl border border-border/70 bg-surface-panel/85 px-3 py-2 shadow-[inset_0_1px_0_rgb(255_255_255_/_0.55)] sm:max-w-[13rem]">
          <div className="mb-1 flex items-center gap-1.5">
            <span className="inline-flex items-center rounded-full border border-border/70 bg-muted/45 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
              {t("previousScope")}
            </span>
          </div>
          <ActionTextLink
            onClick={() => dispatch({ type: "BACK" })}
            className="shrink-0"
            showArrow={false}
          >
            <ChevronLeft className="h-3.5 w-3.5" />
            {t("back")}
          </ActionTextLink>
          <p className="mt-1 text-[11px] leading-relaxed text-muted-foreground">
            {t("reopen", { scope: previousScope.scopeLabel })}
          </p>
        </div>
      )}

      <div className="min-w-0 flex-1 rounded-[1.25rem] border border-border/70 bg-surface-panel/92 px-3.5 py-3 shadow-[inset_0_1px_0_rgb(255_255_255_/_0.55)]">
        <div className="mb-1.5 flex flex-wrap items-center gap-2">
          <span className="inline-flex items-center rounded-full border border-border/70 bg-muted/45 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
            {t("currentScope")}
          </span>
          <span className="inline-flex items-center rounded-full border border-brand/10 bg-brand/5 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.16em] text-brand">
            {sourceKindLabel}
          </span>
        </div>
        <div className="truncate text-sm font-semibold text-foreground">
          {state.resultSet.scopeLabel}
        </div>
        <div className="mt-1 truncate text-xs text-muted-foreground">
          {describeScopeTrail(currentSource)}
        </div>
        {currentSource.type === "pivot" && (
          <p className="mt-2 text-[11px] leading-relaxed text-muted-foreground/80">
            {t("pivotDescription")}
          </p>
        )}
      </div>
    </div>
  );
}
