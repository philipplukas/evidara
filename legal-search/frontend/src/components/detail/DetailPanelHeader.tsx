"use client";

import { Copy, MapPin } from "lucide-react";
import type { DetailViewModel } from "@/lib/types";
import { AccentButton } from "../primitives";
import { Breadcrumbs } from "./Breadcrumbs";

interface DetailPanelHeaderProps {
  detail: DetailViewModel;
  onPin?: (id: string, title: string, type: string) => void;
  isPinned?: boolean;
}

export function DetailPanelHeader({ detail, onPin, isPinned }: DetailPanelHeaderProps) {
  const safeTitle = detail.title.trim().length > 0 ? detail.title : "Untitled document";
  const safeSubtitle = detail.subtitle.trim().length > 0 ? detail.subtitle : "No summary available";
  const translationLabel =
    detail.contentLanguage?.label && detail.contentLanguage.label.trim().length > 0
      ? detail.contentLanguage.label
      : "Translated content";

  return (
    <div className="px-5 py-4 border-b border-border/60">
      {/* Breadcrumbs */}
      {detail.breadcrumbs.length > 0 && <Breadcrumbs items={detail.breadcrumbs} />}

      <div className="flex items-start gap-2 mt-2">
        <h2 className="text-base font-semibold text-foreground flex-1 leading-snug">
          {safeTitle}
        </h2>
        {/* Pin + actions */}
        <div className="flex items-center gap-1 shrink-0">
          {onPin && (
            <AccentButton
              onClick={() => onPin(detail.id, safeTitle, detail.type)}
              active={isPinned}
              title={isPinned ? "Unpin" : "Pin"}
            >
              <MapPin className="w-3 h-3" />
            </AccentButton>
          )}
          <AccentButton
            onClick={() => navigator.clipboard.writeText(safeTitle)}
            title="Copy citation"
          >
            <Copy className="w-3 h-3" />
          </AccentButton>
        </div>
      </div>
      <p className="text-xs text-muted-foreground mt-1">{safeSubtitle}</p>

      {/* Content language indicator */}
      {detail.contentLanguage?.isTranslation && (
        <div className="mt-2 px-2 py-1 rounded-md bg-amber-50 border border-amber-200 text-micro text-amber-700 inline-flex items-center gap-1">
          {translationLabel}
        </div>
      )}
    </div>
  );
}
