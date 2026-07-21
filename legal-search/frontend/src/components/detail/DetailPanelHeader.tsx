"use client";

import { Copy, MapPin, Printer } from "lucide-react";
import { useTranslations } from "next-intl";
import { MetadataList } from "@/components/detail/MetadataList";
import { ShareButton } from "@/components/ui/ShareButton";
import { toast } from "@/hooks/use-toast";
import { AnalyticsEvent, track } from "@/lib/analytics";
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
  const citationText =
    detail.subtitle.trim().length > 0 ? `${safeTitle} - ${safeSubtitle}` : safeTitle;
  const translationLabel =
    detail.contentLanguage?.label && detail.contentLanguage.label.trim().length > 0
      ? detail.contentLanguage.label
      : t("translatedContent");

  return (
    <div className="border-b border-border/60 px-5 py-3.5">
      {detail.breadcrumbs.length > 0 && <Breadcrumbs items={detail.breadcrumbs} />}

      <div className="mt-2 flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <h2 className="max-w-[72ch] text-base font-semibold leading-snug text-foreground">
            {safeTitle}
          </h2>
          <p className="mt-1 max-w-[72ch] text-xs leading-5 text-muted-foreground">
            {safeSubtitle}
          </p>

          {detail.contentLanguage?.isTranslation && (
            <div className="mt-2 inline-flex items-center gap-1 rounded-full border border-attention-border bg-attention-subtle px-2.5 py-1 text-tiny font-medium text-attention">
              {translationLabel}
            </div>
          )}

          {detail.metadata.length > 0 ? (
            <div className="mt-3 rounded-lg border border-border/60 bg-muted/20 px-3 py-2">
              <MetadataList showHeading={false} fields={detail.metadata} initialDensity="compact" />
            </div>
          ) : null}
        </div>

        <div className="flex shrink-0 items-center gap-1 pt-0.5">
          {onPin && (
            <AccentButton
              onClick={() => onPin(detail.id, safeTitle, detail.type)}
              active={isPinned}
              title={isPinned ? t("unpin") : t("pin")}
              className="min-w-11 sm:min-w-0"
            >
              <MapPin className="h-3 w-3" />
            </AccentButton>
          )}
          <ShareButton size="sm" className="min-h-11 min-w-11 sm:min-h-0 sm:min-w-0" />
          <AccentButton
            onClick={() => window.print()}
            title={t("print")}
            className="min-w-11 sm:min-w-0"
          >
            <Printer className="h-3 w-3" />
          </AccentButton>
          <AccentButton
            onClick={() => {
              navigator.clipboard.writeText(citationText);
              toast.success(t("copyCitation"));
              track(AnalyticsEvent.SHARE_LINK_COPIED, {});
            }}
            title={t("copyCitation")}
            className="min-w-11 sm:min-w-0"
          >
            <Copy className="h-3 w-3" />
          </AccentButton>
        </div>
      </div>
    </div>
  );
}
