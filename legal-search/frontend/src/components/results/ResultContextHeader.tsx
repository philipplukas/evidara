"use client";

import type { SearchResultViewModel } from "@/lib/types";
import { ExactMatchStrip } from "./ExactMatchStrip";
import { ResultSetScopeBar } from "./ResultSetScopeBar";

interface ResultContextHeaderProps {
  exactMatches?: SearchResultViewModel[];
  onSelect: (id: string) => void;
}

/**
 * Groups the two orientation signals at the top of the center panel:
 *
 * - ExactMatchStrip: "trust this, we found it precisely"
 * - ResultSetScopeBar: "here's where you are, and you can go back"
 *
 * Together they answer: "what kind of result context am I in?"
 */
export function ResultContextHeader({ exactMatches, onSelect }: ResultContextHeaderProps) {
  const hasExactMatches = exactMatches && exactMatches.length > 0;

  return (
    <div className="border-b border-border/60 bg-linear-to-b from-surface-page/70 via-surface-page/35 to-transparent">
      {hasExactMatches && (
        <div className="px-4 pt-4 sm:px-5">
          <ExactMatchStrip matches={exactMatches} onSelect={onSelect} />
        </div>
      )}
      <ResultSetScopeBar />
    </div>
  );
}
