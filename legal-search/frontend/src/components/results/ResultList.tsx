"use client";

import { ArrowRight, Download, RotateCcw, Search } from "lucide-react";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useRef, useState } from "react";
import { ErrorState } from "@/components/ui/error-state";
import { usePreferences } from "@/hooks/use-preferences";
import { hasActiveSearchConstraints, useSearchConstraints } from "@/lib/search-constraints-store";
import type { ResultSetSource, SearchResultViewModel } from "@/lib/types";
import { useWorkspace } from "@/lib/workspace-store";
import { ResultCard } from "./ResultCard";

function describeScopeTrail(
  source: ResultSetSource,
  scopeSearchFn: (query: string) => string,
): string {
  if (source.type === "search") {
    return scopeSearchFn(source.query);
  }

  return `${describeScopeTrail(source.parentSource, scopeSearchFn)} \u00b7 ${source.label}`;
}

function escapeCsvField(value: string): string {
  if (value.includes(",") || value.includes('"') || value.includes("\n")) {
    return `"${value.replace(/"/g, '""')}"`;
  }
  return value;
}

function getEmptyStateCopy(
  source: ResultSetSource,
  t: (key: string, values?: Record<string, string>) => string,
  { query, hasActiveFilters }: { query?: string; hasActiveFilters: boolean },
) {
  if (source.type === "pivot") {
    return {
      title: t("pivotNoResults"),
      body: t("pivotHint"),
      showResetAction: false,
    };
  }

  if (query) {
    if (hasActiveFilters) {
      return {
        title: t("noResultsFiltered"),
        body: t("noResultsFilteredHint"),
        showResetAction: true,
      };
    }
    return {
      title: t("noResults", { query }),
      body: t("noResultsHint"),
      showResetAction: false,
    };
  }

  return {
    title: t("startTitle"),
    body: t("startHint"),
    showResetAction: false,
  };
}

interface ResultListProps {
  results: SearchResultViewModel[];
  selectedId: string | null;
  onFocus: (id: string) => void;
  onPivot: (label: string, sourceId: string) => void;
  onPin: (id: string, title: string, type: string) => void;
  pinnedIds: Set<string>;
  /** When true, show a loading state instead of results */
  isLoading?: boolean;
  /** Optional query string for contextual empty state */
  query?: string;
  /** When true, show an error state instead of results */
  isError?: boolean;
  /** Callback to retry the failed operation */
  onRetry?: () => void;
  /** Callback to trigger a new search */
  onSearch?: (query: string) => void;
}

export function ResultList({
  results,
  selectedId,
  onFocus,
  onPivot,
  onPin,
  pinnedIds,
  isLoading,
  query,
  isError,
  onRetry,
  onSearch: _onSearch,
}: ResultListProps) {
  const { preferences } = usePreferences();
  const pageSize = preferences.resultsPerPage;
  const [visibleCount, setVisibleCount] = useState<number>(pageSize);
  const { state } = useWorkspace();
  const { state: constraints, dispatch: dispatchConstraints } = useSearchConstraints();
  const hasActiveFilters = hasActiveSearchConstraints(constraints);
  const tList = useTranslations("results.list");
  const tEmpty = useTranslations("results.empty");
  const resultSignature = results.map((result) => result.id).join("|");
  const previousResultSignatureRef = useRef(resultSignature);

  useEffect(() => {
    if (previousResultSignatureRef.current === resultSignature) {
      return;
    }

    previousResultSignatureRef.current = resultSignature;
    setVisibleCount(pageSize);
  }, [resultSignature, pageSize]);

  const handleExportCsv = useCallback(() => {
    const header = ["Title", "Type", "Subtitle", "Snippet"].map(escapeCsvField).join(",");
    const rows = results.map((r) =>
      [r.title, r.type, r.subtitle, r.snippet].map(escapeCsvField).join(","),
    );
    const csv = [header, ...rows].join("\n");
    const bom = "\uFEFF";
    const blob = new Blob([bom + csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "results.csv";
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  }, [results]);

  const visibleResults = results.slice(0, visibleCount);
  const hasMore = visibleCount < results.length;
  const currentSource = state.resultSet.source;
  const scopeTrail = describeScopeTrail(currentSource, (q) => tList("scopeSearch", { query: q }));
  const resultsSummary =
    visibleResults.length === results.length
      ? tList("resultCount", { count: results.length })
      : tList("resultCountPartial", {
          visible: visibleResults.length,
          total: results.length,
        });

  if (isLoading) {
    return (
      <div
        className="flex flex-col items-center justify-center py-20 text-center"
        role="status"
        aria-live="polite"
      >
        <div className="w-8 h-8 border-2 border-accent-core border-t-transparent rounded-full animate-spin mb-4" />
        <p className="text-sm font-medium text-foreground">{tList("searchingScope")}</p>
        <p className="mt-1 max-w-sm text-xs text-muted-foreground">{scopeTrail}</p>
      </div>
    );
  }

  if (isError) {
    return (
      <ErrorState
        message={tEmpty("searchFailed")}
        description={tEmpty("searchFailedDescription")}
        onRetry={onRetry}
      />
    );
  }

  if (results.length === 0) {
    const emptyState = getEmptyStateCopy(currentSource, tEmpty, { query, hasActiveFilters });

    return (
      <div
        className="flex flex-col items-center justify-center py-20 text-center"
        role="status"
        aria-live="polite"
      >
        <div className="w-12 h-12 rounded-full bg-muted flex items-center justify-center mb-4">
          <Search className="w-5 h-5 text-muted-foreground/40" />
        </div>
        <h3 className="mb-1 text-sm font-medium text-foreground">{emptyState.title}</h3>
        <p className="max-w-xs text-xs text-muted-foreground">{emptyState.body}</p>
        {emptyState.showResetAction && (
          <button
            type="button"
            onClick={() => dispatchConstraints({ type: "RESET_ALL" })}
            className="mt-4 inline-flex items-center gap-1.5 rounded-lg border border-border bg-background px-3 py-1.5 text-xs font-medium text-muted-foreground transition-colors hover:border-accent-core/30 hover:bg-muted/40 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring"
          >
            <RotateCcw className="h-3 w-3" />
            {tEmpty("resetFiltersAction")}
          </button>
        )}
      </div>
    );
  }

  return (
    <div>
      <div aria-live="polite" aria-atomic="true" className="sr-only">
        {resultsSummary}
      </div>
      {/* Result summary */}
      <div className="flex flex-col gap-1 border-b border-border/60 px-4 py-3 sm:flex-row sm:items-start sm:justify-between sm:gap-4 sm:px-5">
        <div className="min-w-0">
          <h2 className="block text-xs font-semibold text-foreground">{resultsSummary}</h2>
          <span className="block truncate text-[11px] text-muted-foreground">{scopeTrail}</span>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <span
            className="inline-flex items-center rounded-full bg-muted px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.16em] text-muted-foreground"
            title={tList("sortedByRelevanceHelp")}
          >
            {tList("sortedByRelevance")}
          </span>
          <button
            type="button"
            onClick={handleExportCsv}
            className="inline-flex items-center gap-1 rounded-full border border-border/70 bg-transparent px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.16em] text-muted-foreground transition-colors hover:border-accent-core/30 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring"
          >
            <Download className="h-3 w-3" />
            {tList("exportCsv")}
          </button>
        </div>
      </div>

      {/* Results */}
      {visibleResults.map((result) => (
        <ResultCard
          key={result.id}
          result={result}
          isSelected={selectedId === result.id}
          onFocus={onFocus}
          onPivot={onPivot}
          onPin={onPin}
          isPinned={pinnedIds.has(result.id)}
        />
      ))}

      {/* Load more */}
      {hasMore && (
        <div className="border-t border-border/60 px-4 py-4 sm:px-5">
          <button
            type="button"
            onClick={() => setVisibleCount((c) => c + pageSize)}
            className="inline-flex w-full items-center justify-center gap-2 rounded-lg border border-border
              bg-background px-4 py-3 text-sm font-medium text-muted-foreground transition-colors
              hover:border-accent-core/20 hover:bg-muted/40 hover:text-foreground"
          >
            <span>{tList("loadMore")}</span>
            <ArrowRight className="h-3.5 w-3.5" />
            <span className="text-xs text-muted-foreground/60">
              {tList("remaining", { count: results.length - visibleCount })}
            </span>
          </button>
        </div>
      )}
    </div>
  );
}
