"use client";

import { FileText } from "lucide-react";
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
  const activeTab = useActiveTab();

  if (!detail) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-center px-6">
        <div className="w-14 h-14 rounded-full bg-muted/50 flex items-center justify-center mb-4">
          <FileText className="w-6 h-6 text-muted-foreground/40" />
        </div>
        <h3 className="text-sm font-medium text-muted-foreground mb-1">Select a result</h3>
        <p className="text-xs text-muted-foreground/70 max-w-[200px]">
          Click on a search result to view its details, related materials, and references.
        </p>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col">
      {/* Stable header — stays constant across tab switches */}
      <DetailPanelHeader detail={detail} onPin={onPin} isPinned={isPinned} />

      {/* URL-driven tab bar */}
      <DetailTabs tabs={detail.tabs} />

      {/* Tab content */}
      <div className="flex-1 overflow-y-auto">
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
        {activeTab === "structure" && detail.localStructure && (
          <StructureTab items={detail.localStructure.items} onFocus={onFocus} />
        )}
      </div>
    </div>
  );
}
