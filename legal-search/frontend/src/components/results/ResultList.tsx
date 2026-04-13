"use client";

import { Search } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { ResultSetSource, SearchResultViewModel } from "@/lib/types";
import { useWorkspace } from "@/lib/workspace-store";
import { ResultCard } from "./ResultCard";

const PAGE_SIZE = 10;

function describeScopeTrail(source: ResultSetSource): string {
  if (source.type === "search") {
    return `Search for "${source.query}"`;
  }

  return `${describeScopeTrail(source.parentSource)} · ${source.label}`;
}

function getEmptyStateCopy(source: ResultSetSource, query?: string) {
  if (source.type === "pivot") {
    return {
      title: "No results in this pivot",
      body: "Return to the previous scope or try a different related count to keep moving.",
    };
  }

  if (query) {
    return {
      title: `No results for "${query}"`,
      body: "Try broadening the query or adjusting filters to widen the result set.",
    };
  }

  return {
    title: "Start searching",
    body: "Enter a query above to explore legal documents, court decisions, and commentary.",
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
}: ResultListProps) {
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);
  const { state } = useWorkspace();
  const resultSignature = results.map((result) => result.id).join("|");
  const previousResultSignatureRef = useRef(resultSignature);

  useEffect(() => {
    if (previousResultSignatureRef.current === resultSignature) {
      return;
    }

    previousResultSignatureRef.current = resultSignature;
    setVisibleCount(PAGE_SIZE);
  }, [resultSignature]);

  const visibleResults = results.slice(0, visibleCount);
  const hasMore = visibleCount < results.length;
  const currentSource = state.resultSet.source;
  const scopeTrail = describeScopeTrail(currentSource);

  if (isLoading) {
    return (
      <div
        className="flex flex-col items-center justify-center py-20 text-center"
        role="status"
        aria-live="polite"
      >
        <div className="w-8 h-8 border-2 border-brand border-t-transparent rounded-full animate-spin mb-4" />
        <p className="text-sm font-medium text-foreground">Searching current scope…</p>
        <p className="mt-1 max-w-sm text-xs text-muted-foreground">{scopeTrail}</p>
      </div>
    );
  }

  if (results.length === 0) {
    const emptyState = getEmptyStateCopy(currentSource, query);

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
      </div>
    );
  }

  return (
    <div>
      {/* Result count */}
      <div className="flex flex-col gap-2 px-4 py-3 border-b border-border/60 sm:flex-row sm:items-start sm:justify-between sm:gap-3 sm:px-5">
        <div className="min-w-0">
          <span className="block text-xs font-semibold text-foreground">
            {results.length} results
          </span>
          <span className="block truncate text-xs text-muted-foreground">{scopeTrail}</span>
        </div>
        <span className="shrink-0 text-[10px] font-semibold uppercase tracking-[0.16em] text-muted-foreground/70">
          Sorted by relevance
        </span>
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
        <div className="px-5 py-4 text-center border-t border-border/60">
          <button
            type="button"
            onClick={() => setVisibleCount((c) => c + PAGE_SIZE)}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg border border-border
              text-sm font-medium text-muted-foreground hover:text-foreground hover:bg-muted
              transition-colors"
          >
            Load more results
            <span className="text-xs text-muted-foreground/60">
              ({results.length - visibleCount} remaining)
            </span>
          </button>
        </div>
      )}
    </div>
  );
}
