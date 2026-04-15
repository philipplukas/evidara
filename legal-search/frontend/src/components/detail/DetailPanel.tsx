"use client";

import { FileText } from "lucide-react";
import { useTranslations } from "next-intl";
import type { DetailViewModel } from "@/lib/types";
import { DetailPanelHeader } from "./DetailPanelHeader";
import { DetailTabs, useActiveTab } from "./DetailTabs";
import { AnnotationTab } from "./tabs/AnnotationTab";
import { DetailsTab } from "./tabs/DetailsTab";
import { ReferencesTab } from "./tabs/ReferencesTab";
import { RelatedTab } from "./tabs/RelatedTab";
import { StructureTab } from "./tabs/StructureTab";

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
        className="flex h-full min-h-0 items-center justify-center px-4 py-8 text-center sm:px-6"
        role="status"
        aria-live="polite"
      >
        <div className="w-full max-w-[24rem] rounded-3xl border border-border/70 bg-surface-shell/45 px-6 py-7 shadow-[inset_0_1px_0_rgba(255,255,255,0.6)]">
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-interactive-accent-subtle text-brand">
            <FileText className="h-5 w-5" />
          </div>
          <p className="mt-4 text-tiny uppercase tracking-[0.18em] text-muted-foreground/70">
            Document detail
          </p>
          <h3 className="mt-2 text-base font-semibold text-foreground">No result selected</h3>
          <p className="mx-auto mt-2 max-w-[20rem] text-sm leading-6 text-muted-foreground">
            Choose a result to open the document detail, related materials, and references.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
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
        {activeTab === "structure" &&
          (detail.localStructure?.items?.length ? (
            <StructureTab items={detail.localStructure.items} onFocus={onFocus} />
          ) : (
            <DetailEmptyState
              title={t("empty.noStructureTitle")}
              description={t("empty.noStructureDescription")}
            />
          ))}
      </div>
    </div>
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
