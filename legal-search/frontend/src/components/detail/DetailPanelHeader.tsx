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
    <div className="border-b border-border/60 px-5 py-3.5">
      {detail.breadcrumbs.length > 0 && <Breadcrumbs items={detail.breadcrumbs} />}

      <div className="mt-2 flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <h2 className="text-base font-semibold leading-snug text-foreground">{safeTitle}</h2>
          <p className="mt-1 text-xs leading-5 text-muted-foreground">{safeSubtitle}</p>

          {detail.contentLanguage?.isTranslation && (
            <div className="mt-2 inline-flex items-center gap-1 rounded-full border border-amber-200 bg-amber-50 px-2.5 py-1 text-tiny font-medium text-amber-700">
              {translationLabel}
            </div>
          )}
        </div>

        <div className="flex shrink-0 items-center gap-1 pt-0.5">
          {onPin && (
            <AccentButton
              onClick={() => onPin(detail.id, safeTitle, detail.type)}
              active={isPinned}
              title={isPinned ? "Unpin" : "Pin"}
            >
              <MapPin className="h-3 w-3" />
            </AccentButton>
          )}
          <AccentButton
            onClick={() => navigator.clipboard.writeText(safeTitle)}
            title="Copy citation"
          >
            <Copy className="h-3 w-3" />
          </AccentButton>
        </div>
      </div>
    </div>
  );
}
