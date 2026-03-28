"use client";

import type { SearchResultViewModel } from "@/lib/types";
import { ResultCard } from "./ResultCard";

interface ResultListProps {
  results: SearchResultViewModel[];
  selectedId: string | null;
  onFocus: (id: string) => void;
  onPivot: (label: string, sourceId: string) => void;
  onPin: (id: string, title: string, type: string) => void;
  pinnedIds: Set<string>;
}

export function ResultList({
  results,
  selectedId,
  onFocus,
  onPivot,
  onPin,
  pinnedIds,
}: ResultListProps) {
  if (results.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-center">
        <div className="w-12 h-12 rounded-full bg-muted flex items-center justify-center mb-4">
          <span className="text-xl text-muted-foreground">⚖</span>
        </div>
        <h3 className="text-sm font-medium text-foreground mb-1">No results found</h3>
        <p className="text-xs text-muted-foreground max-w-xs">
          Try adjusting your search query or filters to find what you&apos;re looking for.
        </p>
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
      {results.map((result) => (
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
    </div>
  );
}
