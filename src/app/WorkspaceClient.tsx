"use client";

import { useCallback, useEffect, useRef } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import {
  ResizablePanelGroup,
  ResizablePanel,
  ResizableHandle,
  PanelImperativeHandle,
} from "@/components/ui/resizable-panels";
import { useDesktop } from "@/hooks/use-desktop";
import { useWorkspace } from "@/lib/workspace-store";
import { useDetail } from "@/hooks/use-detail";
import { AppHeader } from "@/components/layout/AppHeader";
import { ContextBar } from "@/components/layout/ContextBar";
import { FilterPanel } from "@/components/filters/FilterPanel";
import { ResultContextHeader } from "@/components/results/ResultContextHeader";
import { ResultList } from "@/components/results/ResultList";
import { DetailPanel } from "@/components/detail/DetailPanel";
import { MobileWorkspace } from "@/components/layout/MobileWorkspace";
import type {
  SearchContextViewModel,
  FilterViewModel,
} from "@/lib/types";

interface WorkspaceClientProps {
  searchContext: SearchContextViewModel;
  filters: FilterViewModel[];
}

export default function WorkspaceClient({
  searchContext,
  filters,
}: WorkspaceClientProps) {
  const isDesktop = useDesktop();
  const { state, dispatch } = useWorkspace();

  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const leftRef = useRef<PanelImperativeHandle>(null);
  const rightRef = useRef<PanelImperativeHandle>(null);

  // ─── URL-driven selection ───
  const selectedId = searchParams.get("item");
  const isDetailOpen = Boolean(selectedId);
  const { data: detail } = useDetail(selectedId);

  const setSelectedId = useCallback(
    (id: string | null) => {
      const params = new URLSearchParams(searchParams.toString());
      if (id) {
        params.set("item", id);
      } else {
        params.delete("item");
      }
      const next = params.toString();
      router.replace(next ? `${pathname}?${next}` : pathname, {
        scroll: false,
      });
    },
    [pathname, router, searchParams]
  );

  const handleSelect = useCallback(
    (id: string) => {
      setSelectedId(id);
      dispatch({
        type: "PUSH_TRAIL",
        entry: {
          id,
          title:
            state.resultSet.items.find((r) => r.id === id)?.title ?? id,
          type:
            state.resultSet.items.find((r) => r.id === id)?.type ??
            "unknown",
          timestamp: Date.now(),
        },
      });
    },
    [setSelectedId, dispatch, state.resultSet.items]
  );

  const handlePivot = useCallback(
    (label: string, sourceId: string) => {
      // In real app, BFF call. For now, import pivot data lazily.
      import("@/lib/mock-data").then(({ pivotDecisionsForArt754 }) => {
        dispatch({
          type: "PIVOT",
          source: {
            type: "pivot",
            label,
            parentSource: state.resultSet.source,
          },
          results: pivotDecisionsForArt754,
          scopeLabel: `${label} for ${state.resultSet.items.find((r) => r.id === sourceId)?.title ?? sourceId}`,
        });
      });
    },
    [dispatch, state.resultSet]
  );

  const handlePin = useCallback(
    (id: string, title: string, type: string) => {
      if (state.pinned.some((p) => p.id === id)) {
        dispatch({ type: "UNPIN", id });
      } else {
        dispatch({ type: "PIN", item: { id, title, type } });
      }
    },
    [dispatch, state.pinned]
  );

  const pinnedIds = new Set(state.pinned.map((p) => p.id));

  // ─── Desktop panel sync ───
  useEffect(() => {
    if (!isDesktop) return;
    if (isDetailOpen) {
      rightRef.current?.expand();
    } else {
      rightRef.current?.collapse();
    }
  }, [isDesktop, isDetailOpen]);

  // ─── Escape to close ───
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

  // ─── Mobile ───
  if (!isDesktop) {
    return (
      <MobileWorkspace
        searchContext={searchContext}
        filters={filters}
        results={state.resultSet.items}
        selectedId={selectedId}
        detail={detail ?? null}
        onFocus={handleSelect}
        onPivot={handlePivot}
        onPin={handlePin}
        pinnedIds={pinnedIds}
        onCloseDetail={() => setSelectedId(null)}
      />
    );
  }

  // ─── Desktop ───
  return (
    <div className="flex flex-col h-screen bg-[#fafafa]">
      <AppHeader />
      <ContextBar context={searchContext} />

      <div className="flex-1 min-h-0">
        <ResizablePanelGroup
          direction="horizontal"
          className="h-full"
        >
          {/* Left: Filters */}
          <ResizablePanel
            panelRef={leftRef}
            defaultSize={18}
            minSize={12}
            maxSize={28}
            collapsible
            collapsedSize={4}
          >
            <div className="h-full overflow-y-auto bg-white border-r border-border">
              <FilterPanel filters={filters} />
            </div>
          </ResizablePanel>

          <ResizableHandle withHandle />

          {/* Center: Results */}
          <ResizablePanel
            defaultSize={isDetailOpen ? 46 : 78}
            minSize={30}
          >
            <div className="h-full overflow-y-auto bg-white">
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
            <div className="h-full overflow-y-auto bg-white border-l border-border">
              <DetailPanel
                detail={detail ?? null}
                onFocus={handleSelect}
                onPivot={handlePivot}
                onPin={handlePin}
                isPinned={
                  selectedId ? pinnedIds.has(selectedId) : false
                }
              />
            </div>
          </ResizablePanel>
        </ResizablePanelGroup>
      </div>
    </div>
  );
}
