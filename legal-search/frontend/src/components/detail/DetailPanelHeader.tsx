"use client";

import { Copy, MapPin } from "lucide-react";
import { useTranslations } from "next-intl";
import { MetadataList } from "@/components/detail/MetadataList";
import { enrichMetadataRows } from "@/lib/metadata-visibility";
import type { DetailViewModel } from "@/lib/types";
import { AccentButton } from "../primitives";
import { Breadcrumbs } from "./Breadcrumbs";

interface DetailPanelHeaderProps {
  detail: DetailViewModel;
  onPin?: (id: string, title: string, type: string) => void;
  isPinned?: boolean;
}

export function DetailPanelHeader({ detail, onPin, isPinned }: DetailPanelHeaderProps) {
  const t = useTranslations("detail");
  const safeTitle = detail.title.trim().length > 0 ? detail.title : t("fallbackTitle");
  const safeSubtitle = detail.subtitle.trim().length > 0 ? detail.subtitle : t("fallbackSubtitle");
  const translationLabel =
    detail.contentLanguage?.label && detail.contentLanguage.label.trim().length > 0
      ? detail.contentLanguage.label
      : t("translatedContent");

  return (
    <div className="border-b border-border/60 px-5 py-3.5">
      {detail.breadcrumbs.length > 0 && <Breadcrumbs items={detail.breadcrumbs} />}

      <div className="mt-2 flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <h2 className="text-base font-semibold leading-snug text-foreground">{safeTitle}</h2>
          <p className="mt-1 text-xs leading-5 text-muted-foreground">{safeSubtitle}</p>

          {detail.contentLanguage?.isTranslation && (
            <div className="mt-2 inline-flex items-center gap-1 rounded-full border border-attention-border bg-attention-subtle px-2.5 py-1 text-tiny font-medium text-attention">
              {translationLabel}
            </div>
          )}

          {detail.metadata.length > 0 ? (
            <div className="mt-3 border-t border-border/50 pt-3">
              <MetadataList
                showHeading={false}
                fields={enrichMetadataRows(detail.metadata, detail.type)}
                initialDensity="compact"
              />
            </div>
          ) : null}
        </div>

        <div className="flex shrink-0 items-center gap-1 pt-0.5">
          {onPin && (
            <AccentButton
              onClick={() => onPin(detail.id, safeTitle, detail.type)}
              active={isPinned}
              title={isPinned ? t("unpin") : t("pin")}
            >
              <MapPin className="h-3 w-3" />
            </AccentButton>
          )}
          <AccentButton
            onClick={() => navigator.clipboard.writeText(safeTitle)}
            title={t("copyCitation")}
          >
            <Copy className="h-3 w-3" />
          </AccentButton>
        </div>
      </div>
    </div>
  );
}
