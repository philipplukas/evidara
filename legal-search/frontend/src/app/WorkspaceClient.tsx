"use client";

import { useTranslations } from "next-intl";
import { parseAsString, useQueryState } from "nuqs";
import { useCallback, useEffect, useRef, useState } from "react";
import { DetailPanel } from "@/components/detail/DetailPanel";
import { FilterPanel } from "@/components/filters/FilterPanel";
import { AppHeader } from "@/components/layout/AppHeader";
import { ContextBar } from "@/components/layout/ContextBar";
import { MobileWorkspace } from "@/components/layout/MobileWorkspace";
import { ResultContextHeader } from "@/components/results/ResultContextHeader";
import { ResultList } from "@/components/results/ResultList";
import { ResultSetScopeBar } from "@/components/results/ResultSetScopeBar";
import { DetailPanelSkeleton } from "@/components/skeletons";
import {
  type PanelImperativeHandle,
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from "@/components/ui/resizable-panels";
import { useDesktop } from "@/hooks/use-desktop";
import { useDetail } from "@/hooks/use-detail";
import { runSearch } from "@/hooks/use-search";
import { useSearchConstraints } from "@/lib/search-constraints-store";
import type { FilterViewModel, SearchContextViewModel } from "@/lib/types";
import { useWorkspace } from "@/lib/workspace-store";

interface WorkspaceClientProps {
  searchContext: SearchContextViewModel;
  filters: FilterViewModel[];
  showControlPlaneEntry?: boolean;
}

export default function WorkspaceClient({
  searchContext,
  filters,
  showControlPlaneEntry = true,
}: WorkspaceClientProps) {
  const t = useTranslations();
  const isDesktop = useDesktop();
  const { state, dispatch } = useWorkspace();
  const { state: constraints } = useSearchConstraints();
  const [activeFilters, setActiveFilters] = useState(filters);

  useEffect(() => {
    setActiveFilters(filters);
  }, [filters]);

  // URL state via nuqs — replaces manual useSearchParams + router.replace
  const [selectedId, setSelectedId] = useQueryState("item", parseAsString);

  const leftRef = useRef<PanelImperativeHandle>(null);
  const rightRef = useRef<PanelImperativeHandle>(null);

  const isDetailOpen = Boolean(selectedId);
  const {
    data: detail,
    isLoading: isDetailLoading,
    isError: isDetailError,
  } = useDetail(selectedId);

  const handleSelect = useCallback(
    (id: string) => {
      setSelectedId(id);
      const item = state.resultSet.items.find((r) => r.id === id);
      dispatch({
        type: "PUSH_TRAIL",
        entry: {
          id,
          title: item?.title ?? id,
          type: item?.type ?? "unknown",
          timestamp: Date.now(),
        },
      });
    },
    [setSelectedId, dispatch, state.resultSet.items],
  );

  const handlePivot = useCallback(
    async (label: string, sourceId: string) => {
      const sourceResult = state.resultSet.items.find((r) => r.id === sourceId);
      const pivotQuery = sourceResult?.title ?? label;
      const { results, filters: nextFilters } = await runSearch(pivotQuery, constraints);
      setActiveFilters(nextFilters);
      dispatch({
        type: "PIVOT",
        source: {
          type: "pivot",
          label,
          parentSource: state.resultSet.source,
        },
        results,
        scopeLabel: `${label} for ${state.resultSet.items.find((r) => r.id === sourceId)?.title ?? sourceId}`,
      });
    },
    [dispatch, state.resultSet, constraints],
  );

  const handleSearch = useCallback(
    async (query: string) => {
      const { results, filters: nextFilters } = await runSearch(query, constraints);
      setActiveFilters(nextFilters);
      dispatch({ type: "SEARCH", query, results });
    },
    [constraints, dispatch],
  );

  const handlePin = useCallback(
    (id: string, title: string, type: string) => {
      if (state.pinned.some((p) => p.id === id)) {
        dispatch({ type: "UNPIN", id });
      } else {
        dispatch({ type: "PIN", item: { id, title, type } });
      }
    },
    [dispatch, state.pinned],
  );

  const pinnedIds = new Set(state.pinned.map((p) => p.id));

  // Desktop panel sync
  useEffect(() => {
    if (!isDesktop) return;
    if (isDetailOpen) {
      rightRef.current?.expand();
    } else {
      rightRef.current?.collapse();
    }
  }, [isDesktop, isDetailOpen]);

  // Escape to close
  useEffect(() => {
    if (!isDesktop || !isDetailOpen) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setSelectedId(null);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [isDesktop, isDetailOpen, setSelectedId]);

  // Detail content — show skeleton during load, error message on failure
  const detailContent = isDetailLoading ? (
    <DetailPanelSkeleton />
  ) : isDetailError ? (
    <div className="flex flex-col items-center justify-center h-full text-center px-6">
      <p className="text-sm text-destructive">{t("workspace.detailLoadFailed")}</p>
    </div>
  ) : (
    <DetailPanel
      detail={detail ?? null}
      onFocus={handleSelect}
      onPivot={handlePivot}
      onPin={handlePin}
      isPinned={selectedId ? pinnedIds.has(selectedId) : false}
    />
  );

  // Mobile
  if (!isDesktop) {
    return (
      <MobileWorkspace
        searchContext={searchContext}
        filters={activeFilters}
        results={state.resultSet.items}
        selectedId={selectedId}
        detail={detail ?? null}
        onFocus={handleSelect}
        onPivot={handlePivot}
        onPin={handlePin}
        pinnedIds={pinnedIds}
        onCloseDetail={() => setSelectedId(null)}
        showControlPlaneEntry={showControlPlaneEntry}
      />
    );
  }

  // Desktop
  return (
    <div className="flex flex-col h-screen bg-surface-page">
      <AppHeader onSearch={handleSearch} showControlPlaneEntry={showControlPlaneEntry} />
      <ContextBar context={searchContext} />

      <div className="flex-1 min-h-0">
        <ResizablePanelGroup direction="horizontal" className="h-full">
          {/* Left: Filters */}
          <ResizablePanel
            panelRef={leftRef}
            defaultSize={18}
            minSize={12}
            maxSize={28}
            collapsible
            collapsedSize={4}
          >
            <div className="h-full overflow-y-auto bg-surface-panel border-r border-border">
              <FilterPanel filters={activeFilters} />
            </div>
          </ResizablePanel>

          <ResizableHandle withHandle />

          {/* Center: Results */}
          <ResizablePanel defaultSize={isDetailOpen ? 46 : 78} minSize={30}>
            <div className="h-full overflow-y-auto bg-surface-panel">
              <ResultSetScopeBar />
              <ResultContextHeader
                exactMatches={searchContext.exactMatches}
                onSelect={handleSelect}
              />

              <ResultList
                results={state.resultSet.items}
                selectedId={selectedId}
                onFocus={handleSelect}
                onPivot={handlePivot}
                onPin={handlePin}
                pinnedIds={pinnedIds}
              />
            </div>
          </ResizablePanel>

          <ResizableHandle withHandle />

          {/* Right: Detail — collapsed by default */}
          <ResizablePanel
            panelRef={rightRef}
            defaultSize={0}
            minSize={25}
            maxSize={45}
            collapsible
            collapsedSize={0}
          >
            <div className="h-full overflow-y-auto bg-surface-panel border-l border-border">
              {detailContent}
            </div>
          </ResizablePanel>
        </ResizablePanelGroup>
      </div>
    </div>
  );
}
