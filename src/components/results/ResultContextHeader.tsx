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
export function ResultContextHeader({
  exactMatches,
  onSelect,
}: ResultContextHeaderProps) {
  const hasExactMatches = exactMatches && exactMatches.length > 0;

  return (
    <div>
      {hasExactMatches && (
        <div className="px-5 pt-4">
          <ExactMatchStrip matches={exactMatches} onSelect={onSelect} />
        </div>
      )}
      <ResultSetScopeBar />
    </div>
  );
}
