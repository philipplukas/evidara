"use client";

import { Search } from "lucide-react";
import { useState } from "react";
import type { SearchResultViewModel } from "@/lib/types";
import { ResultCard } from "./ResultCard";

const PAGE_SIZE = 10;

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

  // Reset visible count when results change
  const visibleResults = results.slice(0, visibleCount);
  const hasMore = visibleCount < results.length;

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-center">
        <div className="w-8 h-8 border-2 border-brand border-t-transparent rounded-full animate-spin mb-4" />
        <p className="text-sm text-muted-foreground">Searching…</p>
      </div>
    );
  }

  if (results.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-center">
        <div className="w-12 h-12 rounded-full bg-muted flex items-center justify-center mb-4">
          <Search className="w-5 h-5 text-muted-foreground/40" />
        </div>
        {query ? (
          <>
            <h3 className="text-sm font-medium text-foreground mb-1">
              No results for &ldquo;{query}&rdquo;
            </h3>
            <p className="text-xs text-muted-foreground max-w-xs">
              Try adjusting your search query or filters to find what you&apos;re looking for.
            </p>
          </>
        ) : (
          <>
            <h3 className="text-sm font-medium text-foreground mb-1">Start searching</h3>
            <p className="text-xs text-muted-foreground max-w-xs">
              Enter a query above to explore legal documents, court decisions, and commentary.
            </p>
          </>
        )}
      </div>
    );
  }

  return (
    <div>
      {/* Result count */}
      <div className="px-5 py-3 border-b border-border/60">
        <span className="text-xs text-muted-foreground">
          <span className="font-semibold text-foreground">{results.length}</span> results
          {" · "}
          <span className="text-muted-foreground/70">sorted by relevance</span>
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
