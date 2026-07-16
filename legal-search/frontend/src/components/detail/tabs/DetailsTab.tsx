"use client";

import { useTranslations } from "next-intl";
import { MetadataList } from "@/components/detail/MetadataList";
import { enrichMetadataRows } from "@/lib/metadata-visibility";
import type { DetailViewModel } from "@/lib/types";
import { SectionLabel } from "../../primitives";
import { DocumentBody } from "../DocumentBody";
import { TabEmptyState } from "./TabEmptyState";

interface DetailsTabProps {
  detail: DetailViewModel;
}

export function DetailsTab({ detail }: DetailsTabProps) {
  const t = useTranslations("detail");
  const hasMetadata = detail.metadata.length > 0;
  const hasContent = Boolean(detail.contentText?.trim());
  const showEmptyState = !hasMetadata && !hasContent;

  return (
    <div className="space-y-5 px-5 py-5">
      <div className="space-y-1">
        <SectionLabel>{t("tabs.documentDetails")}</SectionLabel>
        <p className="max-w-2xl text-xs leading-5 text-muted-foreground">
          {t("descriptions.details")}
        </p>
      </div>

      {hasMetadata && (
        <MetadataList
          fields={enrichMetadataRows(detail.metadata, detail.type)}
          initialDensity="default"
        />
      )}

      {hasContent && detail.contentText && (
        <section className="space-y-3">
          <SectionLabel>{t("tabs.content")}</SectionLabel>
          <DocumentBody text={detail.contentText} />
        </section>
      )}

      {showEmptyState && (
        <TabEmptyState
          title={t("empty.noDocumentDetailsTitle")}
          description={t("empty.noDocumentDetailsDescription")}
        />
      )}
    </div>
  );
}
