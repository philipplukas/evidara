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
import { ResultsControlRegion } from "@/components/results/ResultsControlRegion";
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
  controlPanelUrl?: string;
}

export default function WorkspaceClient({
  searchContext,
  filters,
  showControlPlaneEntry = true,
  controlPanelUrl,
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
  const [urlQuery] = useQueryState("q", parseAsString.withDefault(""));

  const leftRef = useRef<PanelImperativeHandle>(null);
  const rightRef = useRef<PanelImperativeHandle>(null);
  const hasAppliedInitialConstraintsRef = useRef(false);
  const lastSearchSignatureRef = useRef<string>("");
  const searchRequestIdRef = useRef(0);

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

  const createSearchSignature = useCallback(
    (query: string) =>
      JSON.stringify({
        query,
        jurisdictions: constraints.context.jurisdictions,
        languages: constraints.context.languages,
        sourceType: constraints.context.sourceType,
        officialOnly: constraints.context.officialOnly,
        refinements: constraints.refinements,
      }),
    [constraints],
  );

  const executeSearch = useCallback(
    async (query: string) => {
      const requestId = ++searchRequestIdRef.current;
      const signature = createSearchSignature(query);
      const { results, filters: nextFilters } = await runSearch(query, constraints);
      if (requestId !== searchRequestIdRef.current) {
        // Ignore stale responses when newer searches have already started.
        return;
      }
      lastSearchSignatureRef.current = signature;
      setActiveFilters(nextFilters);
      dispatch({ type: "SEARCH", query, results });
    },
    [constraints, dispatch, createSearchSignature],
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

  const handleSearch = executeSearch;

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

  useEffect(() => {
    if (!urlQuery) return;
    if (!hasAppliedInitialConstraintsRef.current) {
      hasAppliedInitialConstraintsRef.current = true;
      const hasNonDefaultConstraints =
        constraints.context.jurisdictions.join(",") !== "ch" ||
        constraints.context.languages.join(",") !== "de" ||
        constraints.context.sourceType !== null ||
        constraints.context.officialOnly ||
        constraints.refinements.length > 0;
      if (!hasNonDefaultConstraints) return;
    }
    const signature = createSearchSignature(urlQuery);
    if (signature === lastSearchSignatureRef.current) {
      return;
    }
    void executeSearch(urlQuery);
  }, [constraints, createSearchSignature, executeSearch, urlQuery]);

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
        onSearch={handleSearch}
        showControlPlaneEntry={showControlPlaneEntry}
        controlPanelUrl={controlPanelUrl}
      />
    );
  }

  // Desktop
  return (
    <div className="flex h-screen flex-col bg-surface-page">
      <AppHeader
        onSearch={handleSearch}
        showControlPlaneEntry={showControlPlaneEntry}
        controlPanelUrl={controlPanelUrl}
      />
      <ContextBar context={searchContext} />

      <div className="min-h-0 flex-1 px-3 pb-3 pt-2 sm:px-4 sm:pb-4">
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
            <div
              className="h-full overflow-y-auto rounded-[1.35rem] border border-border/70 bg-surface-panel"
              style={{ boxShadow: "var(--shadow-raised)" }}
            >
              <FilterPanel filters={activeFilters} />
            </div>
          </ResizablePanel>

          <ResizableHandle withHandle />

          {/* Center: Results */}
          <ResizablePanel defaultSize={isDetailOpen ? 46 : 78} minSize={30}>
            <div
              className="h-full overflow-y-auto rounded-[1.6rem] border border-border/70 bg-surface-panel"
              style={{ boxShadow: "var(--shadow-panel)" }}
            >
              <ResultsControlRegion>
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
              </ResultsControlRegion>
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
            <div
              className="h-full overflow-y-auto rounded-[1.35rem] border border-border/70 bg-surface-panel"
              style={{ boxShadow: "var(--shadow-raised)" }}
            >
              {detailContent}
            </div>
          </ResizablePanel>
        </ResizablePanelGroup>
      </div>
    </div>
  );
}
