"use client";

import { useState } from "react";
import { AppHeader } from "@/components/layout/AppHeader";
import { ContextBar } from "@/components/layout/ContextBar";
import { DetailSheet } from "@/components/layout/DetailSheet";
import { FiltersSheet } from "@/components/layout/FiltersSheet";
import { ExactMatchStrip } from "@/components/results/ExactMatchStrip";
import { ResultList } from "@/components/results/ResultList";
import { ResultSetScopeBar } from "@/components/results/ResultSetScopeBar";
import { ResultsControlRegion } from "@/components/results/ResultsControlRegion";
import type {
  DetailViewModel,
  FilterViewModel,
  SearchContextViewModel,
  SearchResultViewModel,
} from "@/lib/types";

interface MobileWorkspaceProps {
  searchContext: SearchContextViewModel;
  filters: FilterViewModel[];
  results: SearchResultViewModel[];
  selectedId: string | null;
  detail: DetailViewModel | null;
  /** Focus driven from the detail surface (e.g. citation click inside DetailSheet). */
  onFocus: (id: string) => void;
  /**
   * Focus driven from a list surface (result list, exact-match strip). Emits
   * RESULT_FOCUSED_FROM_LIST in addition to the base focus behavior. Falls
   * back to `onFocus` when not supplied so callers can opt in incrementally.
   */
  onFocusFromList?: (id: string) => void;
  onPivot: (label: string, sourceId: string) => void;
  onPin: (id: string, title: string, type: string) => void;
  pinnedIds: Set<string>;
  onCloseDetail: () => void;
  onSearch: (query: string) => Promise<void>;
  showControlPlaneEntry?: boolean;
  controlPanelUrl?: string;
  isSearchError?: boolean;
  onSearchRetry?: () => void;
}

export function MobileWorkspace({
  searchContext,
  filters,
  results,
  selectedId,
  detail,
  onFocus,
  onFocusFromList,
  onPivot,
  onPin,
  pinnedIds,
  onCloseDetail,
  onSearch,
  showControlPlaneEntry = true,
  controlPanelUrl,
  isSearchError,
  onSearchRetry,
}: MobileWorkspaceProps) {
  const focusFromList = onFocusFromList ?? onFocus;
  const [filtersOpen, setFiltersOpen] = useState(false);

  return (
    <div className="mobile-workspace__shell">
      <AppHeader
        onSearch={onSearch}
        onOpenFilters={() => setFiltersOpen(true)}
        showControlPlaneEntry={showControlPlaneEntry}
        controlPanelUrl={controlPanelUrl}
      />
      <ContextBar context={searchContext} />

      <main id="main-content" className="flex-1 min-h-0 overflow-y-auto bg-surface-page">
        <h1 className="sr-only">Evidara Rechtsrecherche</h1>
        <div className="mobile-workspace__sheet">
          <ResultsControlRegion>
            <ResultSetScopeBar />
            {searchContext.exactMatches && searchContext.exactMatches.length > 0 && (
              <div className="px-5 pt-4">
                <ExactMatchStrip matches={searchContext.exactMatches} onSelect={focusFromList} />
              </div>
            )}

            <ResultList
              results={results}
              selectedId={selectedId}
              onFocus={focusFromList}
              onPivot={onPivot}
              onPin={onPin}
              pinnedIds={pinnedIds}
              isError={isSearchError}
              onRetry={onSearchRetry}
            />
          </ResultsControlRegion>
        </div>
      </main>

      <FiltersSheet open={filtersOpen} onOpenChange={setFiltersOpen} filters={filters} />

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
