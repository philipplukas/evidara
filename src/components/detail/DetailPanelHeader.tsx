"use client";

import { MapPin, Copy } from "lucide-react";
import type { DetailViewModel } from "@/lib/types";
import { Breadcrumbs } from "./Breadcrumbs";

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
  );
}
