"use client";

import { FileText } from "lucide-react";
import { useTranslations } from "next-intl";
import type { DetailViewModel } from "@/lib/types";
import { DetailPanelHeader } from "./DetailPanelHeader";
import { DetailTabs, useActiveTab } from "./DetailTabs";
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
// `sections` is the key the API uses for a document's local structure, where
// the mock uses `structure`; both render the outline. They are listed
// separately rather than reconciled because the mock's vocabulary is the one
// that drifted, and the API's is the contract.
const DETAIL_TAB_KEYS = [
  "details",
  "related",
  "references",
  "annotation",
  "structure",
  "sections",
  "content",
];

interface DetailPanelProps {
  detail: DetailViewModel | null;
  onFocus?: (id: string) => void;
  onPivot?: (label: string, sourceId: string) => void;
  onPin?: (id: string, title: string, type: string) => void;
  isPinned?: boolean;
}

export function DetailPanel({ detail, onFocus, onPivot, onPin, isPinned }: DetailPanelProps) {
  const t = useTranslations("detail");
  const activeTab = useActiveTab();

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
      <DetailTabs tabs={detail.tabs} />
      <div className="min-h-0 flex-1 overflow-y-auto">
        {activeTab === "details" && <DetailsTab detail={detail} />}
        {activeTab === "related" && (
          <RelatedTab
            groups={detail.relatedGroups}
            onFocus={onFocus}
            onPivot={onPivot}
            sourceId={detail.id}
          />
        )}
        {activeTab === "references" && (
          <ReferencesTab
            references={detail.references}
            onFocus={onFocus}
            onPivot={onPivot}
            sourceId={detail.id}
            sourceTitle={detail.title}
          />
        )}
        {activeTab === "annotation" && <AnnotationTab annotations={detail.annotations} />}
        {/* Inhalt renders the document body. It used to render the structure
            outline, so a tab labelled "Inhalt" showed a heading reading
            "LOKALE STRUKTUR" — the outline, never the text (#609). */}
        {activeTab === "content" &&
          (detail.contentText?.trim() ? (
            <div className="px-5 py-5">
              <DocumentBody text={detail.contentText} />
            </div>
          ) : (
            <DetailEmptyState
              title={t("empty.noContentTitle")}
              description={t("empty.noContentDescription")}
            />
          ))}
        {(activeTab === "structure" || activeTab === "sections") &&
          (detail.localStructure?.items?.length ? (
            <StructureTab items={detail.localStructure.items} onFocus={onFocus} />
          ) : (
            <DetailEmptyState
              title={t("empty.noStructureTitle")}
              description={t("empty.noStructureDescription")}
            />
          ))}
        {/* Contract drift guard: a tab key with no dedicated renderer above
            shows a graceful empty state instead of a blank panel. */}
        {!DETAIL_TAB_KEYS.includes(activeTab) && (
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
