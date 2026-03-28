"use client";

import { useState } from "react";
import { AppHeader } from "@/components/layout/AppHeader";
import { ContextBar } from "@/components/layout/ContextBar";
import { ExactMatchStrip } from "@/components/results/ExactMatchStrip";
import { ResultList } from "@/components/results/ResultList";
import { FiltersSheet } from "@/components/layout/FiltersSheet";
import { DetailSheet } from "@/components/layout/DetailSheet";
import type {
  SearchResultViewModel,
  SearchContextViewModel,
  FilterViewModel,
  DetailViewModel,
} from "@/lib/types";

interface MobileWorkspaceProps {
  searchContext: SearchContextViewModel;
  filters: FilterViewModel[];
  results: SearchResultViewModel[];
  selectedId: string | null;
  detail: DetailViewModel | null;
  onFocus: (id: string) => void;
  onPivot: (label: string, sourceId: string) => void;
  onPin: (id: string, title: string, type: string) => void;
  pinnedIds: Set<string>;
  onCloseDetail: () => void;
}

export function MobileWorkspace({
  searchContext,
  filters,
  results,
  selectedId,
  detail,
  onFocus,
  onPivot,
  onPin,
  pinnedIds,
  onCloseDetail,
}: MobileWorkspaceProps) {
  const [filtersOpen, setFiltersOpen] = useState(false);

  return (
    <div className="flex flex-col h-screen bg-surface-page">
      <AppHeader onOpenFilters={() => setFiltersOpen(true)} />
      <ContextBar context={searchContext} />

      <div className="flex-1 min-h-0 overflow-y-auto bg-surface-panel">
        {searchContext.exactMatches &&
          searchContext.exactMatches.length > 0 && (
            <div className="px-5 pt-4">
              <ExactMatchStrip
                matches={searchContext.exactMatches}
                onSelect={onFocus}
              />
            </div>
          )}

        <ResultList
          results={results}
          selectedId={selectedId}
          onFocus={onFocus}
          onPivot={onPivot}
          onPin={onPin}
          pinnedIds={pinnedIds}
        />
      </div>

      <FiltersSheet
        open={filtersOpen}
        onOpenChange={setFiltersOpen}
        filters={filters}
      />

      <DetailSheet
        open={Boolean(selectedId)}
        onOpenChange={(open) => {
          if (!open) onCloseDetail();
        }}
        detail={detail}
        onFocus={onFocus}
        onPivot={onPivot}
        onPin={onPin}
        isPinned={selectedId ? pinnedIds.has(selectedId) : false}
      />
    </div>
  );
}
