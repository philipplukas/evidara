"use client";

import DOMPurify from "dompurify";
import { useTranslations } from "next-intl";
import { useMemo } from "react";
import { MetadataSection } from "@/components/detail/MetadataSection";
import type { DetailViewModel } from "@/lib/types";
import { SectionLabel } from "../../primitives";
import { TabEmptyState } from "./TabEmptyState";

interface DetailsTabProps {
  detail: DetailViewModel;
}

export function DetailsTab({ detail }: DetailsTabProps) {
  const t = useTranslations("detail");
  const sanitizedContentHtml = useMemo(() => {
    if (!detail.contentHtml) {
      return "";
    }
    return DOMPurify.sanitize(detail.contentHtml);
  }, [detail.contentHtml]);
  const hasMetadata = detail.metadata.length > 0;
  const hasContent = Boolean(sanitizedContentHtml.trim());
  const showEmptyState = !hasMetadata && !hasContent;

  return (
    <div className="space-y-5 px-5 py-5">
      <div className="space-y-1">
        <SectionLabel>{t("tabs.documentDetails")}</SectionLabel>
        <p className="max-w-2xl text-xs leading-5 text-muted-foreground">
          {t("descriptions.details")}
        </p>
      </div>

      {hasMetadata && <MetadataSection rows={detail.metadata} />}

      {hasContent && (
        <section className="space-y-3">
          <SectionLabel>{t("tabs.content")}</SectionLabel>
          <div
            className="max-w-[72ch] text-sm leading-7 text-foreground/88 prose-sm font-document
              [&_.article-marginal]:text-micro [&_.article-marginal]:font-semibold [&_.article-marginal]:text-muted-foreground
              [&_.article-marginal]:mt-3 [&_.article-marginal]:mb-1
              [&_strong]:text-foreground [&_strong]:font-semibold
              [&_h4]:text-xs [&_h4]:font-semibold [&_h4]:uppercase [&_h4]:tracking-wider [&_h4]:text-muted-foreground [&_h4]:mt-4 [&_h4]:mb-2
              [&_p]:mb-3 [&_p:last-child]:mb-0
              [&_ul]:my-3 [&_ol]:my-3
              [&_li]:mb-1"
            dangerouslySetInnerHTML={{ __html: sanitizedContentHtml }}
          />
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
