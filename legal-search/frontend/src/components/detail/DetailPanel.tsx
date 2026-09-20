"use client";

import { FileText } from "lucide-react";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useDocumentOutline } from "@/hooks/use-document-outline";
import { useReaderScrollSpy } from "@/hooks/use-reader-scroll-spy";
import type { DetailViewModel } from "@/lib/types";
import { DetailPanelHeader } from "./DetailPanelHeader";
import { DetailTabs, useDetailTab } from "./DetailTabs";
import { DocumentBody } from "./DocumentBody";
import { AnnotationTab } from "./tabs/AnnotationTab";
import { DetailsTab } from "./tabs/DetailsTab";
import { ReferencesTab } from "./tabs/ReferencesTab";
import { RelatedTab } from "./tabs/RelatedTab";
import { StructureTab } from "./tabs/StructureTab";

// Tab keys DetailPanel knows how to render. The contract's `TabView.key` is a
// free-form string, and the real API emits `content` (Inhalt) — a key the mock
// never used and this panel did not handle, so selecting it rendered a blank
// void. Any key not listed here now falls through to a graceful empty state.
//
// The API and the mock use different vocabularies for two tabs that render the
// same panel, so each is an alias group rather than a single key:
//
//   - `sections` (API) / `structure` (mock) — the local outline.
//   - `citations` (API) / `references` (mock) — the reference groups. The API
//     only ever emits `citations` (`document-detail.mapper.ts` `composeTabs`),
//     so the panel previously handled a key the API never sends while missing
//     the one it always does: the tab appeared, was clickable, and confidently
//     rendered "nothing here" over real citation data (#622).
//
// Each group is declared once and used by both the guard below and the render
// branch it drives — the two drifting apart is what produced #609 and #622.
const REFERENCE_TAB_KEYS: string[] = ["references", "citations"];
const STRUCTURE_TAB_KEYS: string[] = ["structure", "sections"];
/** The tab that renders the body. Where a section jump sends the reader. */
export const CONTENT_TAB_KEY = "content";
const DETAIL_TAB_KEYS: string[] = [
  "details",
  "related",
  "annotation",
  CONTENT_TAB_KEY,
  ...REFERENCE_TAB_KEYS,
  ...STRUCTURE_TAB_KEYS,
];

/**
 * Tabs that reading mode does not show, because its rails render them beside
 * the text instead (#1053).
 *
 * Leaving them in the strip would put the outline in two places at once, and
 * the two would answer "which section am I in" differently — the tab has no
 * scroll spy. Derived from the alias groups above so a renamed key cannot
 * leave a duplicate behind.
 */
const RAIL_OWNED_TAB_KEYS: string[] = [...STRUCTURE_TAB_KEYS, ...REFERENCE_TAB_KEYS];

/** A request from outside the panel to move the reader to a section. */
export interface SectionJump {
  sectionId: string;
  /**
   * Increments per request. Without it, choosing the same section twice — after
   * scrolling away from it — is the same prop value and scrolls nowhere.
   */
  requestId: number;
}

interface DetailPanelProps {
  detail: DetailViewModel | null;
  onFocus?: (id: string) => void;
  onPivot?: (label: string, sourceId: string) => void;
  onPin?: (id: string, title: string, type: string) => void;
  isPinned?: boolean;
  /**
   * `"reader"` is desktop reading mode: the outline and the references are
   * rails outside this panel, the body is set at the reading measure, and the
   * panel reports which section the reader is in. `"panel"` is the historical
   * tabbed detail panel, still what mobile renders.
   */
  layout?: "panel" | "reader";
  /** A section jump requested by the outline rail. Reader layout only. */
  sectionJump?: SectionJump | null;
  /** The section the reader is currently inside. Reader layout only. */
  onActiveSectionChange?: (sectionId: string | null) => void;
}

export function DetailPanel({
  detail,
  onFocus,
  onPivot,
  onPin,
  isPinned,
  layout = "panel",
  sectionJump = null,
  onActiveSectionChange,
}: DetailPanelProps) {
  const t = useTranslations("detail");
  const [activeTab, setActiveTab] = useDetailTab();
  const [focusedSectionId, setFocusedSectionId] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const isReader = layout === "reader";

  // One alignment of outline to body per document, through one function, so
  // the outline and the text cannot disagree about which sections exist in the
  // body — see `use-document-outline.ts`.
  const outline = useDocumentOutline(detail);

  // In reader layout the rails own the outline and the references, so their
  // tabs come out of the strip and a URL that still names one lands on the
  // body rather than on a tab that is no longer there.
  const visibleTabs = useMemo(
    () =>
      isReader
        ? (detail?.tabs ?? []).filter((tab) => !RAIL_OWNED_TAB_KEYS.includes(tab.key))
        : (detail?.tabs ?? []),
    [detail?.tabs, isReader],
  );
  const effectiveTab =
    isReader && RAIL_OWNED_TAB_KEYS.includes(activeTab) ? CONTENT_TAB_KEY : activeTab;

  // Selecting a section moves the reader. It does NOT select a document: the
  // outline hands out `section_id`s, and feeding one to the workspace's
  // document selection is what made every outline click a 404 (#1040).
  const handleSectionSelect = useCallback(
    (id: string) => {
      setFocusedSectionId(id);
      void setActiveTab(CONTENT_TAB_KEY);
    },
    [setActiveTab],
  );

  // A jump requested by the outline rail is the same move, from outside.
  const jumpRequestId = sectionJump?.requestId;
  const jumpSectionId = sectionJump?.sectionId;
  useEffect(() => {
    if (jumpRequestId === undefined || !jumpSectionId) return;
    setFocusedSectionId(jumpSectionId);
    // A rail jump does not switch tabs when the reader is already on the body;
    // it does when the user has stepped away to Details.
    void setActiveTab(CONTENT_TAB_KEY);
  }, [jumpRequestId, jumpSectionId, setActiveTab]);

  // The heading only exists once the content tab has rendered, so the scroll
  // waits for the tab rather than happening in the click handler.
  // biome-ignore lint/correctness/useExhaustiveDependencies: `jumpRequestId` re-scrolls a repeated jump to the same section
  useEffect(() => {
    if (!focusedSectionId || effectiveTab !== CONTENT_TAB_KEY) return;
    const container = scrollRef.current;
    if (!container) return;
    const target = Array.from(container.querySelectorAll<HTMLElement>("[data-section-id]")).find(
      (element) => element.dataset.sectionId === focusedSectionId,
    );
    // jsdom implements no layout, so this is absent under Vitest. The tab
    // switch and the anchor's presence are what the tests assert.
    if (target && typeof target.scrollIntoView === "function") {
      target.scrollIntoView({ block: "start" });
    }
  }, [focusedSectionId, effectiveTab, jumpRequestId]);

  // Report the reader's position to whatever renders the outline beside it.
  // `noop` keeps the hook's dependency stable when nothing is listening —
  // reader layout is the only caller that passes a handler.
  const noopSectionChange = useCallback(() => {}, []);
  const spyBodyKey = `${detail?.id ?? ""}:${effectiveTab}`;
  useReaderScrollSpy(scrollRef, spyBodyKey, onActiveSectionChange ?? noopSectionChange);

  if (!detail) {
    return (
      <div
        className="flex flex-col items-center justify-center py-20 text-center"
        role="status"
        aria-live="polite"
      >
        <div className="w-12 h-12 rounded-full bg-muted flex items-center justify-center mb-4">
          <FileText className="w-5 h-5 text-muted-foreground/40" />
        </div>
        <h3 className="mb-1 text-sm font-medium text-muted-foreground">{t("empty.noSelection")}</h3>
        <p className="max-w-xs text-xs text-muted-foreground">{t("empty.description")}</p>
      </div>
    );
  }

  return (
    <section aria-label="Dokumentdetail" className="flex h-full min-h-0 flex-col">
      <DetailPanelHeader detail={detail} onPin={onPin} isPinned={isPinned} />
      <DetailTabs tabs={visibleTabs} />
      <div ref={scrollRef} data-testid="detail-scroll" className="min-h-0 flex-1 overflow-y-auto">
        {effectiveTab === "details" && <DetailsTab detail={detail} outline={outline} />}
        {effectiveTab === "related" && (
          <RelatedTab
            groups={detail.relatedGroups}
            onFocus={onFocus}
            onPivot={onPivot}
            sourceId={detail.id}
          />
        )}
        {REFERENCE_TAB_KEYS.includes(effectiveTab) && (
          <ReferencesTab
            references={detail.references}
            onFocus={onFocus}
            onPivot={onPivot}
            sourceId={detail.id}
            sourceTitle={detail.title}
          />
        )}
        {effectiveTab === "annotation" && <AnnotationTab annotations={detail.annotations} />}
        {/* Inhalt renders the document body. It used to render the structure
            outline, so a tab labelled "Inhalt" showed a heading reading
            "LOKALE STRUKTUR" — the outline, never the text (#609). */}
        {effectiveTab === CONTENT_TAB_KEY &&
          (detail.contentText?.trim() ? (
            <div className={isReader ? "px-6 py-6" : "px-5 py-5"}>
              <DocumentBody
                text={detail.contentText}
                outline={outline}
                measure={isReader ? "reader" : "panel"}
              />
            </div>
          ) : (
            <DetailEmptyState
              title={t("empty.noContentTitle")}
              description={t("empty.noContentDescription")}
            />
          ))}
        {STRUCTURE_TAB_KEYS.includes(effectiveTab) &&
          (detail.localStructure?.items?.length ? (
            <StructureTab
              items={detail.localStructure.items}
              onSelectSection={handleSectionSelect}
              anchoredIds={outline.anchored}
              activeSectionId={focusedSectionId}
            />
          ) : (
            <DetailEmptyState
              title={t("empty.noStructureTitle")}
              description={t("empty.noStructureDescription")}
            />
          ))}
        {/* Contract drift guard: a tab key with no dedicated renderer above
            shows a graceful empty state instead of a blank panel. */}
        {!DETAIL_TAB_KEYS.includes(effectiveTab) && (
          <DetailEmptyState
            title={t("empty.noContentTitle")}
            description={t("empty.noContentDescription")}
          />
        )}
      </div>
    </section>
  );
}

function DetailEmptyState({ title, description }: { title: string; description: string }) {
  return (
    <div className="p-5">
      <div className="rounded-2xl border border-dashed border-border/70 bg-muted/25 px-4 py-5 text-center">
        <h3 className="text-sm font-semibold text-foreground">{title}</h3>
        <p className="mx-auto mt-1.5 max-w-[20rem] text-xs leading-5 text-muted-foreground">
          {description}
        </p>
      </div>
    </div>
  );
}
