"use client";

import { MapPin, Copy } from "lucide-react";
import type { DetailViewModel } from "@/lib/types";
import { Breadcrumbs } from "./Breadcrumbs";
import { AccentButton } from "../primitives";

interface DetailPanelHeaderProps {
  detail: DetailViewModel;
  onPin?: (id: string, title: string, type: string) => void;
  isPinned?: boolean;
}

export function DetailPanelHeader({ detail, onPin, isPinned }: DetailPanelHeaderProps) {
  return (
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
            <AccentButton
              onClick={() => onPin(detail.id, detail.title, detail.type)}
              active={isPinned}
              title={isPinned ? "Unpin" : "Pin"}
            >
              <MapPin className="w-3 h-3" />
            </AccentButton>
          )}
          <AccentButton
            onClick={() => navigator.clipboard.writeText(detail.title)}
            title="Copy citation"
          >
            <Copy className="w-3 h-3" />
          </AccentButton>
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
  );
}
