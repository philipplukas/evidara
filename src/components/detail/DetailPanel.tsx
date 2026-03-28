"use client";

import { useState } from "react";
import {
  ChevronRight,
  ExternalLink,
  Info,
  FileText,
  MessageSquare,
  BookOpen,
  MapPin,
  ArrowRight,
  Copy,
} from "lucide-react";
import type {
  DetailViewModel,
  RelatedGroup,
  ReferenceGroup,
  AnnotationViewModel,
  LocalStructureItem,
  MetadataRow,
} from "@/lib/types";
import { getIcon } from "@/lib/icons";
import { getBadgeColor } from "../results/ExactMatchStrip";

interface DetailPanelProps {
  detail: DetailViewModel | null;
  onFocus?: (id: string) => void;
  onPivot?: (label: string, sourceId: string) => void;
  onPin?: (id: string, title: string, type: string) => void;
  isPinned?: boolean;
}

export function DetailPanel({ detail, onFocus, onPivot, onPin, isPinned }: DetailPanelProps) {
  const [activeTab, setActiveTab] = useState("details");

  if (!detail) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-center px-6">
        <div className="w-14 h-14 rounded-full bg-muted/50 flex items-center justify-center mb-4">
          <FileText className="w-6 h-6 text-muted-foreground/40" />
        </div>
        <h3 className="text-sm font-medium text-muted-foreground mb-1">
          Select a result
        </h3>
        <p className="text-xs text-muted-foreground/70 max-w-[200px]">
          Click on a search result to view its details, related materials, and references.
        </p>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="px-5 py-4 border-b border-border/60">
        {/* Breadcrumbs */}
        {detail.breadcrumbs.length > 0 && (
          <Breadcrumbs items={detail.breadcrumbs} />
        )}

        <div className="flex items-start gap-2 mt-2">
          <h2 className="text-base font-semibold text-foreground flex-1 leading-snug">
            {detail.title}
          </h2>
          {/* Pin + actions */}
          <div className="flex items-center gap-1 shrink-0">
            {onPin && (
              <button
                onClick={() => onPin(detail.id, detail.title, detail.type)}
                className={`flex items-center gap-1 px-2 py-1 rounded text-[11px] font-medium transition-all
                  ${isPinned
                    ? "text-[#2563eb] bg-[#2563eb]/10"
                    : "text-muted-foreground hover:text-[#2563eb] hover:bg-[#2563eb]/5"
                  }`}
                title={isPinned ? "Unpin" : "Pin"}
              >
                <MapPin className="w-3 h-3" />
              </button>
            )}
            <button
              onClick={() => {
                navigator.clipboard.writeText(detail.title);
              }}
              className="flex items-center gap-1 px-2 py-1 rounded text-[11px] font-medium
                text-muted-foreground hover:text-[#2563eb] hover:bg-[#2563eb]/5 transition-all"
              title="Copy citation"
            >
              <Copy className="w-3 h-3" />
            </button>
          </div>
        </div>
        <p className="text-xs text-muted-foreground mt-0.5">{detail.subtitle}</p>

        {/* Content language indicator */}
        {detail.contentLanguage?.isTranslation && (
          <div className="mt-2 px-2 py-1 rounded bg-amber-50 border border-amber-100 text-[11px] text-amber-700 inline-block">
            {detail.contentLanguage.label}
          </div>
        )}
      </div>

      {/* Tabs */}
      <div className="flex border-b border-border/60 px-2">
        {detail.tabs.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`px-3 py-2.5 text-xs font-medium border-b-2 transition-colors
              ${
                activeTab === tab.key
                  ? "border-[#2563eb] text-[#2563eb]"
                  : "border-transparent text-muted-foreground hover:text-foreground"
              }`}
          >
            {tab.label}
            {tab.count != null && (
              <span className="ml-1 text-[10px] text-muted-foreground/60">
                {tab.count}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="flex-1 overflow-y-auto">
        {activeTab === "details" && (
          <DetailsTab detail={detail} />
        )}
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
        {activeTab === "annotation" && (
          <AnnotationTab annotations={detail.annotations} />
        )}
        {activeTab === "structure" && detail.localStructure && (
          <StructureTab items={detail.localStructure.items} onFocus={onFocus} />
        )}
      </div>
    </div>
  );
}

// ─── Sub-components ───

function Breadcrumbs({ items }: { items: string[] }) {
  return (
    <div className="flex items-center gap-1 text-[11px] text-muted-foreground/70 flex-wrap">
      {items.map((item, i) => (
        <span key={i} className="flex items-center gap-1">
          {i > 0 && <ChevronRight className="w-2.5 h-2.5" />}
          <span className={i === items.length - 1 ? "font-medium text-foreground/60" : ""}>
            {item}
          </span>
        </span>
      ))}
    </div>
  );
}

function DetailsTab({ detail }: { detail: DetailViewModel }) {
  return (
    <div className="p-5 space-y-5">
      {/* Metadata */}
      <MetadataSection rows={detail.metadata} />

      {/* Content */}
      {detail.contentHtml && (
        <div className="space-y-2">
          <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Content
          </h4>
          <div
            className="text-sm leading-relaxed text-foreground/85 prose-sm
              [&_.article-marginal]:text-[11px] [&_.article-marginal]:font-semibold [&_.article-marginal]:text-muted-foreground
              [&_.article-marginal]:mt-3 [&_.article-marginal]:mb-1
              [&_strong]:text-foreground [&_strong]:font-semibold
              [&_h4]:text-xs [&_h4]:font-semibold [&_h4]:uppercase [&_h4]:tracking-wider [&_h4]:text-muted-foreground [&_h4]:mt-4 [&_h4]:mb-2
              [&_p]:mb-2"
            style={{ fontFamily: "'Source Serif 4', 'Georgia', serif" }}
            dangerouslySetInnerHTML={{ __html: detail.contentHtml }}
          />
        </div>
      )}
    </div>
  );
}

function MetadataSection({ rows }: { rows: MetadataRow[] }) {
  if (rows.length === 0) return null;
  return (
    <div className="space-y-2">
      <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
        Metadata
      </h4>
      <div className="space-y-1.5">
        {rows.map((row, i) => {
          const icon = getIcon(row.iconKey);
          return (
            <div key={i} className="flex items-baseline gap-2 text-xs">
              <span className="text-muted-foreground w-28 shrink-0 font-medium">
                {row.label}
              </span>
              <span className="text-foreground/80 flex items-center gap-1">
                {icon && <span className="text-sm">{icon}</span>}
                {row.value}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function RelatedTab({
  groups,
  onFocus,
  onPivot,
  sourceId,
}: {
  groups: RelatedGroup[];
  onFocus?: (id: string) => void;
  onPivot?: (label: string, sourceId: string) => void;
  sourceId: string;
}) {
  return (
    <div className="p-5 space-y-5">
      {groups.map((group, i) => (
        <div key={i}>
          <div className="flex items-center justify-between mb-3">
            <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
              {group.groupLabel}
              <span className="text-[10px] font-normal text-muted-foreground/60">
                ({group.items.length})
              </span>
            </h4>
            {onPivot && group.items.length > 0 && (
              <button
                onClick={() => onPivot(group.groupLabel, sourceId)}
                className="flex items-center gap-0.5 text-[11px] font-medium text-[#2563eb] hover:text-[#1d4ed8] transition-colors"
              >
                Show all
                <ArrowRight className="w-3 h-3" />
              </button>
            )}
          </div>
          <div className="space-y-1">
            {group.items.map((item) => (
              <div
                key={item.id}
                onClick={() => onFocus?.(item.id)}
                className="flex items-center gap-2 px-3 py-2 rounded-md hover:bg-muted/50 cursor-pointer transition-colors group"
              >
                {item.badge && (
                  <span
                    className="px-1 py-0.5 rounded text-[9px] font-semibold uppercase tracking-wide shrink-0"
                    style={{
                      backgroundColor: getBadgeColor(item.badge.colorKey).bg,
                      color: getBadgeColor(item.badge.colorKey).text,
                    }}
                  >
                    {item.badge.label}
                  </span>
                )}
                <div className="flex-1 min-w-0">
                  <div className="text-xs font-medium text-foreground truncate">
                    {item.title}
                  </div>
                  {item.subtitle && (
                    <div className="text-[11px] text-muted-foreground truncate">
                      {item.subtitle}
                    </div>
                  )}
                </div>
                <ExternalLink className="w-3 h-3 text-muted-foreground/30 group-hover:text-[#2563eb] transition-colors shrink-0" />
              </div>
            ))}
          </div>
        </div>
      ))}
      {groups.length === 0 && (
        <EmptySection label="No related materials" />
      )}
    </div>
  );
}

function ReferencesTab({
  references,
  onFocus,
  onPivot,
  sourceId,
  sourceTitle,
}: {
  references: ReferenceGroup[];
  onFocus?: (id: string) => void;
  onPivot?: (label: string, sourceId: string) => void;
  sourceId: string;
  sourceTitle: string;
}) {
  return (
    <div className="p-5 space-y-5">
      {references.map((group, i) => (
        <div key={i}>
          <div className="flex items-center justify-between mb-3">
            <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              {group.direction}
              <span className="text-[10px] font-normal text-muted-foreground/60 ml-1">
                ({group.items.length})
              </span>
            </h4>
            {onPivot && group.items.length > 0 && (
              <button
                onClick={() => onPivot(`${group.direction} ${sourceTitle}`, sourceId)}
                className="flex items-center gap-0.5 text-[11px] font-medium text-[#2563eb] hover:text-[#1d4ed8] transition-colors"
              >
                Show all
                <ArrowRight className="w-3 h-3" />
              </button>
            )}
          </div>
          <div className="space-y-1">
            {group.items.map((item) => (
              <div
                key={item.id}
                onClick={() => onFocus?.(item.id)}
                className="flex items-center gap-2 px-3 py-2 rounded-md hover:bg-muted/50 cursor-pointer transition-colors"
              >
                <div className="flex-1 min-w-0">
                  <div className="text-xs font-medium text-foreground truncate">
                    {item.title}
                  </div>
                  {item.subtitle && (
                    <div className="text-[11px] text-muted-foreground truncate">
                      {item.subtitle}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      ))}
      {references.length === 0 && (
        <EmptySection label="No references" />
      )}
    </div>
  );
}

function AnnotationTab({ annotations }: { annotations: AnnotationViewModel[] }) {
  if (annotations.length === 0) {
    return (
      <div className="p-5">
        <EmptySection label="No annotations available" />
      </div>
    );
  }

  return (
    <div className="p-5 space-y-4">
      {annotations.map((ann, i) => (
        <div
          key={i}
          className="rounded-lg border border-[#2563eb]/10 bg-[#2563eb]/[0.02] p-4"
        >
          <div className="flex items-center gap-2 mb-2">
            <MessageSquare className="w-3.5 h-3.5 text-[#2563eb]" />
            <h4 className="text-xs font-semibold text-[#2563eb]">
              {ann.title}
            </h4>
          </div>
          <p
            className="text-sm text-foreground/80 leading-relaxed mb-3"
            style={{ fontFamily: "'Source Serif 4', 'Georgia', serif" }}
          >
            {ann.content}
          </p>
          <div className="flex items-center gap-4 text-[11px] text-muted-foreground">
            {ann.provenance && (
              <span className="flex items-center gap-1">
                <Info className="w-3 h-3" />
                {ann.provenance}
              </span>
            )}
            {ann.confidence && (
              <span className="px-1.5 py-0.5 rounded bg-green-50 text-green-700 font-medium text-[10px]">
                {ann.confidence} confidence
              </span>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

function StructureTab({
  items,
  onFocus,
}: {
  items: LocalStructureItem[];
  onFocus?: (id: string) => void;
}) {
  return (
    <div className="p-5">
      <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-3">
        Local Structure
      </h4>
      <div className="space-y-0.5">
        {items.map((item) => (
          <div
            key={item.id}
            onClick={() => onFocus?.(item.id)}
            className={`flex items-center gap-2 px-3 py-2 rounded-md cursor-pointer transition-all text-xs
              ${
                item.active
                  ? "bg-[#2563eb]/5 text-[#2563eb] font-semibold border-l-2 border-l-[#2563eb]"
                  : "text-foreground/70 hover:bg-muted/50 hover:text-foreground border-l-2 border-l-transparent"
              }`}
          >
            <BookOpen className="w-3 h-3 shrink-0" />
            <span className="truncate">{item.label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function EmptySection({ label }: { label: string }) {
  return (
    <div className="text-center py-8">
      <p className="text-xs text-muted-foreground">{label}</p>
    </div>
  );
}
