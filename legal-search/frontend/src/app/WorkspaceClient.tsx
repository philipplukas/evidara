"use client";

import { useTranslations } from "next-intl";
import { parseAsString, useQueryState } from "nuqs";
import { useCallback, useEffect, useRef, useState } from "react";
import { DetailPanel } from "@/components/detail/DetailPanel";
import { DetailUnavailableState } from "@/components/detail/DetailUnavailableState";
import { FilterPanel } from "@/components/filters/FilterPanel";
import { AppHeader } from "@/components/layout/AppHeader";
import { ContextBar } from "@/components/layout/ContextBar";
import { MobileWorkspace } from "@/components/layout/MobileWorkspace";
import { ResultContextHeader } from "@/components/results/ResultContextHeader";
import { ResultList } from "@/components/results/ResultList";
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
import { usePageView } from "@/hooks/use-page-view";
import { usePreferences } from "@/hooks/use-preferences";
import { runSearch } from "@/hooks/use-search";
import { AnalyticsEvent, track } from "@/lib/analytics";
import { useSearchConstraints } from "@/lib/search-constraints-store";
import type { FilterViewModel, SearchContextViewModel } from "@/lib/types";
import { useWorkspace } from "@/lib/workspace-store";

/**
 * Desktop split across the filters / results / detail panels, in percent.
 *
 * Each state must total exactly 100. react-resizable-panels renormalizes any
 * other total against the sum it is given, so a set totalling 96 renders the
 * filter rail at 18/96 ≈ 18.75% — and it snaps back to 18% the moment the
 * detail panel opens, visibly resizing a panel the user never touched.
 */
export const DESKTOP_PANEL_SPLIT = {
  detailClosed: { filters: 18, results: 82, detail: 0 },
  detailOpen: { filters: 18, results: 50, detail: 32 },
} as const;

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
  usePageView();
  const isDesktop = useDesktop();
  const { preferences } = usePreferences();
  const { state, dispatch } = useWorkspace();
  const { state: constraints } = useSearchConstraints();
  const [activeFilters, setActiveFilters] = useState(filters);
  const [searchError, setSearchError] = useState(false);

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
  const split = isDetailOpen ? DESKTOP_PANEL_SPLIT.detailOpen : DESKTOP_PANEL_SPLIT.detailClosed;
  const {
    data: detail,
    isLoading: isDetailLoading,
    isError: isDetailError,
    refetch: refetchDetail,
  } = useDetail(selectedId);
  // Fetch settled successfully but the backend returned 404 (see
  // `hooks/use-detail.ts` — 404 maps to `data: null`). Distinct from
  // "no item selected" where the query is disabled and `data` is also null.
  const isDetailNotFound =
    Boolean(selectedId) && !isDetailLoading && !isDetailError && detail === null;

  const handleCloseDetail = useCallback(() => {
    void setSelectedId(null);
  }, [setSelectedId]);

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
      track(AnalyticsEvent.RESULT_SELECTED, {
        resultId: id,
        resultType: item?.type,
        position: state.resultSet.items.findIndex((r) => r.id === id),
      });
    },
    [setSelectedId, dispatch, state.resultSet.items],
  );

  // Fires only when focus originated in a list surface (result list, exact-match
  // header, mobile list). Paired with — but distinct from — RESULT_SELECTED:
  // RESULT_SELECTED fires on every handleSelect (including citation-driven focus
  // from within the detail panel); FOCUSED_FROM_LIST narrows that to the "user
  // opened a detail from the list" journey step.
  const handleSelectFromList = useCallback(
    (id: string) => {
      handleSelect(id);
      const item = state.resultSet.items.find((r) => r.id === id);
      const position = state.resultSet.items.findIndex((r) => r.id === id);
      // Omit `position` when the focused item isn't in the current result list
      // (e.g. exact-match strip items, which render outside resultSet.items).
      // The schema defines `position` as a non-negative integer, so emitting -1
      // would be out-of-contract.
      track(AnalyticsEvent.RESULT_FOCUSED_FROM_LIST, {
        resultId: id,
        resultType: item?.type,
        ...(position >= 0 ? { position } : {}),
      });
    },
    [handleSelect, state.resultSet.items],
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
      const previousSignature = lastSearchSignatureRef.current;
      const signature = createSearchSignature(query);
      // Classify as a refinement when the query string is unchanged from the
      // last successful search but some constraint dimension flipped. The
      // previous signature is a JSON blob that embeds the prior query — parse
      // defensively so a corrupt snapshot never crashes the search path.
      let isRefinement = false;
      let changedFilterCount = 0;
      if (previousSignature) {
        try {
          const prev = JSON.parse(previousSignature) as {
            query?: string;
            jurisdictions?: string[];
            languages?: string[];
            sourceType?: string | null;
            officialOnly?: boolean;
            refinements?: unknown[];
          };
          if (prev.query === query) {
            const dimensions: Array<boolean> = [
              JSON.stringify(prev.jurisdictions ?? []) !==
                JSON.stringify(constraints.context.jurisdictions),
              JSON.stringify(prev.languages ?? []) !==
                JSON.stringify(constraints.context.languages),
              (prev.sourceType ?? null) !== constraints.context.sourceType,
              Boolean(prev.officialOnly) !== constraints.context.officialOnly,
              JSON.stringify(prev.refinements ?? []) !== JSON.stringify(constraints.refinements),
            ];
            changedFilterCount = dimensions.filter(Boolean).length;
            isRefinement = changedFilterCount > 0;
          }
        } catch {
          // Malformed snapshot — fall through to treating this as a fresh execute.
        }
      }
      // Update the signature ref BEFORE awaiting the request so that rapid
      // successive searches (user submits again before the first response
      // returns) classify against the most-recently-issued signature, not the
      // most-recently-returned one. Otherwise on slow networks refinements
      // get systematically misclassified as fresh executes and the journey
      // telemetry undercounts them.
      lastSearchSignatureRef.current = signature;
      try {
        const { results, filters: nextFilters } = await runSearch(query, constraints, {
          pageSize: preferences.resultsPerPage,
        });
        if (requestId !== searchRequestIdRef.current) {
          // Ignore stale responses when newer searches have already started.
          return;
        }
        setActiveFilters(nextFilters);
        dispatch({ type: "SEARCH", query, results });
        setSearchError(false);
        if (isRefinement) {
          track(AnalyticsEvent.SEARCH_REFINED, {
            query,
            resultCount: results.length,
            changedFilterCount,
          });
        } else {
          track(AnalyticsEvent.SEARCH_EXECUTED, {
            query,
            resultCount: results.length,
            jurisdictions: constraints.context.jurisdictions.join(","),
            languages: constraints.context.languages.join(","),
          });
        }
      } catch {
        setSearchError(true);
      }
    },
    [constraints, dispatch, createSearchSignature, preferences.resultsPerPage],
  );

  const handlePivot = useCallback(
    async (label: string, sourceId: string) => {
      track(AnalyticsEvent.RESULT_PIVOTED, { sourceId, label });
      const sourceResult = state.resultSet.items.find((r) => r.id === sourceId);
      const pivotQuery = sourceResult?.title ?? label;
      const { results, filters: nextFilters } = await runSearch(pivotQuery, constraints, {
        pageSize: preferences.resultsPerPage,
      });
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
    [dispatch, state.resultSet, constraints, preferences.resultsPerPage],
  );

  const handleSearch = executeSearch;

  const handlePin = useCallback(
    (id: string, title: string, type: string) => {
      if (state.pinned.some((p) => p.id === id)) {
        dispatch({ type: "UNPIN", id });
        track(AnalyticsEvent.PIN_REMOVED, { itemId: id });
      } else {
        dispatch({ type: "PIN", item: { id, title, type } });
        track(AnalyticsEvent.PIN_ADDED, { itemId: id, itemType: type });
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

  // Desktop panel sync — use imperative `resize(32)` instead of `expand()` because
  // `expand()` restores to the last-known size, which with `defaultSize={0}` ends up
  // being ~0 (see UX-9). `resize` always sets an explicit width that lands inside
  // the [minSize, maxSize] bounds configured on the panel.
  useEffect(() => {
    if (!isDesktop) return;
    if (isDetailOpen) {
      rightRef.current?.resize(32);
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

  // Detail content — skeleton during load, distinct states for 5xx error vs 404,
  // otherwise render the panel (or the panel's own "no selection" empty state
  // when `detail === null` and no id is selected).
  const detailContent = isDetailLoading ? (
    <DetailPanelSkeleton />
  ) : isDetailError ? (
    <DetailUnavailableState
      role="alert"
      icon="error"
      title={t("workspace.detailLoadFailed")}
      description={t("workspace.detailRetryHint")}
      primaryAction={{
        label: t("workspace.detailRetry"),
        icon: "retry",
        onClick: () => void refetchDetail(),
      }}
      secondaryAction={{
        label: t("workspace.detailClose"),
        onClick: handleCloseDetail,
      }}
    />
  ) : isDetailNotFound ? (
    <DetailUnavailableState
      role="status"
      icon="notFound"
      title={t("workspace.detailNotFound")}
      description={t("workspace.detailNotFoundHint")}
      primaryAction={{
        label: t("workspace.detailClose"),
        icon: "close",
        onClick: handleCloseDetail,
      }}
    />
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
        onFocusFromList={handleSelectFromList}
        onPivot={handlePivot}
        onPin={handlePin}
        pinnedIds={pinnedIds}
        onCloseDetail={() => setSelectedId(null)}
        onSearch={handleSearch}
        showControlPlaneEntry={showControlPlaneEntry}
        controlPanelUrl={controlPanelUrl}
        isSearchError={searchError}
        onSearchRetry={() => {
          if (urlQuery) void executeSearch(urlQuery);
        }}
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

      <main id="main-content" className="shell-frame min-h-0 flex-1 pb-3 pt-2 sm:pb-4">
        <h1 className="sr-only">Evidara Rechtsrecherche</h1>
        <ResizablePanelGroup direction="horizontal" className="h-full">
          {/* Left: Filters */}
          <ResizablePanel
            panelRef={leftRef}
            defaultSize={split.filters}
            minSize={12}
            maxSize={28}
            collapsible
            collapsedSize={4}
          >
            <div
              className="h-full overflow-y-auto rounded-[var(--radius-panel)] border border-border/70 bg-surface-panel"
              style={{ boxShadow: "var(--shadow-raised)" }}
            >
              <FilterPanel filters={activeFilters} />
            </div>
          </ResizablePanel>

          <ResizableHandle withHandle />

          {/* Center: Results */}
          <ResizablePanel defaultSize={split.results} minSize={30}>
            <div
              className="h-full overflow-y-auto rounded-[var(--radius-panel)] border border-border/70 bg-surface-panel"
              style={{ boxShadow: "var(--shadow-panel)" }}
            >
              <ResultsControlRegion>
                <ResultContextHeader
                  exactMatches={searchContext.exactMatches}
                  onSelect={handleSelectFromList}
                />

                <ResultList
                  results={state.resultSet.items}
                  selectedId={selectedId}
                  onFocus={handleSelectFromList}
                  onPivot={handlePivot}
                  onPin={handlePin}
                  pinnedIds={pinnedIds}
                  isError={searchError}
                  onRetry={() => {
                    if (urlQuery) void executeSearch(urlQuery);
                  }}
                  onSearch={handleSearch}
                  query={urlQuery}
                />
              </ResultsControlRegion>
            </div>
          </ResizablePanel>

          <ResizableHandle withHandle />

          {/* Right: Detail — starts at its desired width when already open via URL,
              otherwise collapsed; toggled imperatively via `resize(32)` / `collapse()`
              in the desktop panel sync effect above. */}
          <ResizablePanel
            panelRef={rightRef}
            defaultSize={split.detail}
            minSize={25}
            maxSize={45}
            collapsible
            collapsedSize={0}
          >
            <div
              data-testid="detail-panel"
              className="h-full overflow-y-auto rounded-[var(--radius-panel)] border border-border/70 bg-surface-panel"
              style={{ boxShadow: "var(--shadow-raised)" }}
            >
              {detailContent}
            </div>
          </ResizablePanel>
        </ResizablePanelGroup>
      </main>
    </div>
  );
}
