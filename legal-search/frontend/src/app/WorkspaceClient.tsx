"use client";

import { useTranslations } from "next-intl";
import { useQueryState } from "nuqs";
import { useCallback, useEffect, useRef, useState } from "react";
import { CONTENT_TAB_KEY, DetailPanel, type SectionJump } from "@/components/detail/DetailPanel";
import { useDetailTab } from "@/components/detail/DetailTabs";
import { DetailUnavailableState } from "@/components/detail/DetailUnavailableState";
import { FilterPanel } from "@/components/filters/FilterPanel";
import { AppHeader } from "@/components/layout/AppHeader";
import { ContextBar } from "@/components/layout/ContextBar";
import { MobileWorkspace } from "@/components/layout/MobileWorkspace";
import { EvidenceRail } from "@/components/reader/EvidenceRail";
import { ReaderOutlineRail } from "@/components/reader/ReaderOutlineRail";
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
import { useDocumentOutline } from "@/hooks/use-document-outline";
import { usePageView } from "@/hooks/use-page-view";
import { usePreferences } from "@/hooks/use-preferences";
import { useReadingRailState } from "@/hooks/use-reading-rails";
import { runSearch } from "@/hooks/use-search";
import { AnalyticsEvent, track } from "@/lib/analytics";
import { READING_SPLIT } from "@/lib/reading-layout";
import { useSearchConstraints } from "@/lib/search-constraints-store";
import {
  DEFAULT_DETAIL_TAB,
  DEFAULT_JURISDICTIONS,
  DEFAULT_LANGUAGES,
  searchParamsParsers,
} from "@/lib/search-params";
import type { FilterViewModel, SearchContextViewModel } from "@/lib/types";
import { useWorkspace } from "@/lib/workspace-store";

/**
 * Desktop split across the filters / results / detail panels, in percent.
 *
 * This is the SEARCH layout. Once a document has loaded, the workspace lays
 * itself out as a reading surface instead and the split comes from
 * `READING_SPLIT` in `lib/reading-layout.ts` (#1053).
 *
 * Each state must total exactly 100. react-resizable-panels renormalizes any
 * other total against the sum it is given, so a set totalling 96 renders the
 * filter rail at 18/96 ≈ 18.75% — and it snaps back to 18% the moment the
 * detail panel opens, visibly resizing a panel the user never touched.
 *
 * These values are percentages and MUST reach the panels as `%`-suffixed
 * strings. react-resizable-panels v4 reads a bare number as PIXELS, so passing
 * `32` renders a 32px sliver instead of 32% of the row — which is what silently
 * collapsed the filter rail and detail panel. The library arrived here already
 * at v4 (added at ^4.7.6), so this was never a regression from a working v3:
 * the split was authored in percent against an API that reads numbers as pixels,
 * and the panels rendered as slivers from the start.
 */
export const DESKTOP_PANEL_SPLIT = {
  detailClosed: { filters: 18, results: 82, detail: 0 },
  detailOpen: { filters: 18, results: 50, detail: 32 },
} as const;

/**
 * Width of the collapsed filter rail, in px.
 *
 * Expressed in pixels rather than the previous `4%` so the collapsed rail is a
 * fixed, designed size at every viewport instead of 40px on a laptop and 77px
 * on an ultrawide. `FilterPanel` renders a purpose-built icon rail at this
 * width (see #610); it used to render the full panel clipped into a sliver.
 */
export const FILTER_RAIL_COLLAPSED_PX = 56;

/**
 * Below this width the filter rail is considered collapsed. Sits well above
 * `FILTER_RAIL_COLLAPSED_PX` and well below `minSize` (12% ≈ 173px at 1440),
 * so no legitimate dragged width lands in the gap.
 */
export const FILTER_RAIL_COLLAPSED_THRESHOLD_PX = FILTER_RAIL_COLLAPSED_PX + 8;

/**
 * Below this rendered width a reading rail shows its strip form, in px.
 *
 * Measured rather than derived from the viewport, for the same reason the
 * filter rail is: `lib/reading-layout.ts` decides the DEFAULT width, and the
 * user is then free to drag a rail open at a viewport where the default said
 * strip. Keying the presentation off the rule instead of the rendered size
 * would make that drag do nothing visible.
 *
 * 96px is comfortably above the ~50px a collapsed default produces and well
 * below the ~194px the narrowest listed rail gets (14% at 1400).
 */
export const READING_RAIL_COLLAPSED_THRESHOLD_PX = 96;

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
  const [isFilterRailCollapsed, setIsFilterRailCollapsed] = useState(false);

  useEffect(() => {
    setActiveFilters(filters);
  }, [filters]);

  // URL state via nuqs — replaces manual useSearchParams + router.replace
  const [selectedId, setSelectedId] = useQueryState("item", searchParamsParsers.item);
  const [urlQuery] = useQueryState("q", searchParamsParsers.q);

  const leftRef = useRef<PanelImperativeHandle>(null);
  const rightRef = useRef<PanelImperativeHandle>(null);
  const outlineRef = useRef<PanelImperativeHandle>(null);
  const evidenceRef = useRef<PanelImperativeHandle>(null);
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

  // ─── Reading mode (#1053) ───
  //
  // A document that has LOADED turns the workspace into a reading surface. The
  // skeleton, the 5xx state and the 404 state stay on the search layout: a
  // reading surface whose rails have nothing to put in them would show three
  // empty columns around a spinner, and an empty rail reads as "this document
  // has no outline" rather than "it has not arrived yet".
  const isReadingMode = isDetailOpen && !isDetailLoading && !isDetailError && Boolean(detail);
  const railState = useReadingRailState();
  const readingSplit = READING_SPLIT[railState];
  const outline = useDocumentOutline(detail ?? null);

  const [isOutlineRailCollapsed, setIsOutlineRailCollapsed] = useState(false);
  const [isEvidenceRailCollapsed, setIsEvidenceRailCollapsed] = useState(false);
  const [activeSectionId, setActiveSectionId] = useState<string | null>(null);
  const [sectionJump, setSectionJump] = useState<SectionJump | null>(null);
  const [activeTab, setActiveTab] = useDetailTab();
  const readerOpenedForRef = useRef<string | null>(null);

  const handleCloseDetail = useCallback(() => {
    void setSelectedId(null);
  }, [setSelectedId]);

  // `Panel` exposes no onCollapse/onExpand in react-resizable-panels v4 — the
  // rendered size is the only signal, so derive collapse from it.
  const handleFilterRailResize = useCallback((panelSize: { inPixels: number }) => {
    setIsFilterRailCollapsed(panelSize.inPixels < FILTER_RAIL_COLLAPSED_THRESHOLD_PX);
  }, []);

  const handleOutlineRailResize = useCallback((panelSize: { inPixels: number }) => {
    setIsOutlineRailCollapsed(panelSize.inPixels < READING_RAIL_COLLAPSED_THRESHOLD_PX);
  }, []);

  const handleEvidenceRailResize = useCallback((panelSize: { inPixels: number }) => {
    setIsEvidenceRailCollapsed(panelSize.inPixels < READING_RAIL_COLLAPSED_THRESHOLD_PX);
  }, []);

  // Same reasoning as `handleExpandFilterRail`: `expand()` restores the
  // last-known size, which for a rail that opened collapsed is the collapsed
  // size. Resize to the listed width instead.
  const handleExpandOutlineRail = useCallback(() => {
    outlineRef.current?.resize(`${READING_SPLIT.full.outline}%`);
  }, []);

  const handleExpandEvidenceRail = useCallback(() => {
    evidenceRef.current?.resize(`${READING_SPLIT.full.evidence}%`);
  }, []);

  /** Move the reader to a section of the open document. Never a navigation. */
  const handleSelectSection = useCallback((sectionId: string) => {
    setSectionJump((previous) => ({ sectionId, requestId: (previous?.requestId ?? 0) + 1 }));
  }, []);

  const handleActiveSectionChange = useCallback((sectionId: string | null) => {
    setActiveSectionId(sectionId);
  }, []);

  // A new document is a new position. Without this the rail keeps marking the
  // previous document's section until the next scroll event.
  // biome-ignore lint/correctness/useExhaustiveDependencies: `selectedId` is the trigger, not a read
  useEffect(() => {
    setActiveSectionId(null);
    setSectionJump(null);
  }, [selectedId]);

  // Reading mode opens IN the text. `tab` defaults to `details`, which is the
  // right landing for the tabbed panel and the wrong one for a reading surface
  // — promoting the reader to the centre column and then filling it with a
  // metadata list would promote nothing.
  //
  // Applied once per opened document, so a reader who then chooses "Details"
  // is not bounced back to the body on the next render. A document that
  // carries no body (no `content` tab) is left alone: there is nothing to
  // land in.
  useEffect(() => {
    if (!isReadingMode || !selectedId || !detail) return;
    if (readerOpenedForRef.current === selectedId) return;
    readerOpenedForRef.current = selectedId;
    if (activeTab !== DEFAULT_DETAIL_TAB) return;
    if (!detail.tabs.some((tab) => tab.key === CONTENT_TAB_KEY)) return;
    void setActiveTab(CONTENT_TAB_KEY);
  }, [isReadingMode, selectedId, detail, activeTab, setActiveTab]);

  // `expand()` restores the last-known size, which after a drag-to-collapse is
  // the collapsed size — so resize to the designed default instead (same
  // reasoning as the detail-panel sync effect below).
  const handleExpandFilterRail = useCallback(() => {
    leftRef.current?.resize(`${DESKTOP_PANEL_SPLIT.detailClosed.filters}%`);
  }, []);

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
        const {
          results,
          filters: nextFilters,
          totalResults,
        } = await runSearch(query, constraints, {
          pageSize: preferences.resultsPerPage,
        });
        if (requestId !== searchRequestIdRef.current) {
          // Ignore stale responses when newer searches have already started.
          return;
        }
        setActiveFilters(nextFilters);
        dispatch({ type: "SEARCH", query, results, totalResults });
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
      const {
        results,
        filters: nextFilters,
        totalResults,
      } = await runSearch(pivotQuery, constraints, {
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
        // Localized here rather than in the reducer: the reducer is pure and
        // cannot translate, which is how the sibling search label shipped as
        // English `Results for "…"` into the German UI (#648).
        scopeLabel: t("results.scope.pivotFor", {
          label,
          title: state.resultSet.items.find((r) => r.id === sourceId)?.title ?? sourceId,
        }),
        totalResults,
      });
    },
    [dispatch, state.resultSet, constraints, preferences.resultsPerPage, t],
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

  // NOTE: no `resultSet.source.type === "search"` guard here, unlike the
  // equivalent effect in `AppHeader`. Changing a constraint inside a pivot
  // therefore re-runs the stale `?q=` and throws the user out of the pivot —
  // pre-existing on `main` and tracked as #842, deliberately not fixed in the
  // #822 parser change because the right behaviour is to re-run the *pivot*
  // with the new constraints, which is more than a guard.
  useEffect(() => {
    if (!urlQuery) return;
    if (!hasAppliedInitialConstraintsRef.current) {
      hasAppliedInitialConstraintsRef.current = true;
      const hasNonDefaultConstraints =
        constraints.context.jurisdictions.join(",") !== DEFAULT_JURISDICTIONS.join(",") ||
        constraints.context.languages.join(",") !== DEFAULT_LANGUAGES.join(",") ||
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

  // Desktop panel sync — use imperative `resize` instead of `expand()` because
  // `expand()` restores to the last-known size, which with a collapsed panel ends
  // up being ~0 (see UX-9). `resize` sets an explicit size inside the
  // [minSize, maxSize] bounds configured on the panel.
  //
  // The size MUST be a percentage STRING: react-resizable-panels v4 reads a bare
  // number as PIXELS, so `resize(32)` produced a 32px sliver instead of 32% of
  // the row (≈460px). Same reason the size props below are `%` strings.
  //
  // Reading mode has no collapsible detail panel — the reader IS the centre
  // column — so this only governs the search layout.
  useEffect(() => {
    if (!isDesktop || isReadingMode) return;
    if (isDetailOpen) {
      rightRef.current?.resize(`${DESKTOP_PANEL_SPLIT.detailOpen.detail}%`);
    } else {
      rightRef.current?.collapse();
    }
  }, [isDesktop, isDetailOpen, isReadingMode]);

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
      layout={isReadingMode ? "reader" : "panel"}
      sectionJump={isReadingMode ? sectionJump : null}
      onActiveSectionChange={isReadingMode ? handleActiveSectionChange : undefined}
    />
  );

  /** The result list, narrowed to a strip while reading. Retiring it is #1040. */
  const resultRegion = (
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
        {isReadingMode && detail ? (
          /* Reading mode. The rail state changes the DEFAULT widths, so the
             group is keyed on it: react-resizable-panels reads `defaultSize`
             once per mount, and a crossed breakpoint has to re-apply them. */
          <ResizablePanelGroup
            key={`reading-${railState}`}
            direction="horizontal"
            className="h-full"
            data-testid="reading-mode"
          >
            {/* Filters, collapsed. They answer nothing about a document that
                is already open — but the rail stays, so re-opening them is one
                click and not a lost document. */}
            <ResizablePanel
              panelRef={leftRef}
              defaultSize={`${readingSplit.filters}%`}
              minSize="4%"
              maxSize="24%"
              onResize={handleFilterRailResize}
            >
              <div
                className={`h-full rounded-[var(--radius-panel)] border border-border/70 bg-surface-panel ${
                  isFilterRailCollapsed ? "overflow-hidden" : "overflow-y-auto"
                }`}
                style={{ boxShadow: "var(--shadow-raised)" }}
              >
                <FilterPanel
                  filters={activeFilters}
                  collapsed={isFilterRailCollapsed}
                  onExpand={handleExpandFilterRail}
                />
              </div>
            </ResizablePanel>

            <ResizableHandle withHandle />

            {/* The result strip. Narrow, not gone: dropping it needs a back
                control that restores scroll position and a "next hit"
                affordance first, which is #1040's. */}
            <ResizablePanel
              defaultSize={`${readingSplit.results}%`}
              minSize="8%"
              maxSize="30%"
              data-testid="result-strip"
            >
              <div
                className="h-full overflow-y-auto rounded-[var(--radius-panel)] border border-border/70 bg-surface-panel"
                style={{ boxShadow: "var(--shadow-panel)" }}
              >
                {resultRegion}
              </div>
            </ResizablePanel>

            <ResizableHandle withHandle />

            {/* The outline, on the left where reading order expects it. */}
            <ResizablePanel
              panelRef={outlineRef}
              defaultSize={`${readingSplit.outline}%`}
              minSize="4%"
              maxSize="26%"
              onResize={handleOutlineRailResize}
              data-testid="outline-rail"
            >
              <div
                className="h-full overflow-hidden rounded-[var(--radius-panel)] border border-border/70 bg-surface-panel"
                style={{ boxShadow: "var(--shadow-panel)" }}
              >
                <ReaderOutlineRail
                  items={detail.localStructure?.items ?? []}
                  anchoredIds={outline.anchored}
                  activeSectionId={activeSectionId}
                  onSelectSection={handleSelectSection}
                  collapsed={isOutlineRailCollapsed}
                  onExpand={handleExpandOutlineRail}
                />
              </div>
            </ResizablePanel>

            <ResizableHandle withHandle />

            {/* The reader. The widest column on the screen, which for a product
                whose job is reading law it previously was not. */}
            <ResizablePanel defaultSize={`${readingSplit.reader}%`} minSize="30%">
              <div
                data-testid="detail-panel"
                className="h-full overflow-y-auto rounded-[var(--radius-panel)] border border-border/70 bg-surface-panel"
                style={{ boxShadow: "var(--shadow-raised)" }}
              >
                {detailContent}
              </div>
            </ResizablePanel>

            <ResizableHandle withHandle />

            {/* Evidence. First to collapse — reference, not navigation. */}
            <ResizablePanel
              panelRef={evidenceRef}
              defaultSize={`${readingSplit.evidence}%`}
              minSize="4%"
              maxSize="26%"
              onResize={handleEvidenceRailResize}
              data-testid="evidence-rail"
            >
              <div
                className="h-full overflow-hidden rounded-[var(--radius-panel)] border border-border/70 bg-surface-panel"
                style={{ boxShadow: "var(--shadow-panel)" }}
              >
                <EvidenceRail
                  detail={detail}
                  onFocus={handleSelect}
                  collapsed={isEvidenceRailCollapsed}
                  onExpand={handleExpandEvidenceRail}
                />
              </div>
            </ResizablePanel>
          </ResizablePanelGroup>
        ) : (
          <ResizablePanelGroup direction="horizontal" className="h-full">
            {/* Left: Filters */}
            <ResizablePanel
              panelRef={leftRef}
              defaultSize={`${split.filters}%`}
              minSize="12%"
              maxSize="28%"
              collapsible
              collapsedSize={`${FILTER_RAIL_COLLAPSED_PX}px`}
              onResize={handleFilterRailResize}
            >
              <div
                className={`h-full rounded-[var(--radius-panel)] border border-border/70 bg-surface-panel ${
                  isFilterRailCollapsed ? "overflow-hidden" : "overflow-y-auto"
                }`}
                style={{ boxShadow: "var(--shadow-raised)" }}
              >
                <FilterPanel
                  filters={activeFilters}
                  collapsed={isFilterRailCollapsed}
                  onExpand={handleExpandFilterRail}
                />
              </div>
            </ResizablePanel>

            <ResizableHandle withHandle />

            {/* Center: Results */}
            <ResizablePanel defaultSize={`${split.results}%`} minSize="30%">
              <div
                className="h-full overflow-y-auto rounded-[var(--radius-panel)] border border-border/70 bg-surface-panel"
                style={{ boxShadow: "var(--shadow-panel)" }}
              >
                {resultRegion}
              </div>
            </ResizablePanel>

            <ResizableHandle withHandle />

            {/* Right: Detail — starts at its desired width when already open via URL,
                otherwise collapsed; toggled imperatively via `resize(32)` / `collapse()`
                in the desktop panel sync effect above. */}
            <ResizablePanel
              panelRef={rightRef}
              defaultSize={`${split.detail}%`}
              minSize="25%"
              maxSize="45%"
              collapsible
              collapsedSize="0%"
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
        )}
      </main>
    </div>
  );
}
