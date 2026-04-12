"use client";

import DOMPurify from "dompurify";
import { useMemo } from "react";
import { MetadataSection } from "@/components/detail/MetadataSection";
import type { DetailViewModel } from "@/lib/types";
import { SectionLabel } from "../../primitives";

interface DetailsTabProps {
  detail: DetailViewModel;
}

export function DetailsTab({ detail }: DetailsTabProps) {
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
    <div className="p-5 space-y-5">
      {/* Metadata */}
      {hasMetadata && <MetadataSection rows={detail.metadata} />}

      {/* Content */}
      {hasContent && (
        <div className="space-y-2">
          <SectionLabel>Content</SectionLabel>
          <div
            className="text-sm leading-relaxed text-foreground/85 prose-sm font-document
              [&_.article-marginal]:text-micro [&_.article-marginal]:font-semibold [&_.article-marginal]:text-muted-foreground
              [&_.article-marginal]:mt-3 [&_.article-marginal]:mb-1
              [&_strong]:text-foreground [&_strong]:font-semibold
              [&_h4]:text-xs [&_h4]:font-semibold [&_h4]:uppercase [&_h4]:tracking-wider [&_h4]:text-muted-foreground [&_h4]:mt-4 [&_h4]:mb-2
              [&_p]:mb-2"
            dangerouslySetInnerHTML={{ __html: sanitizedContentHtml }}
          />
        </div>
      )}

      {showEmptyState && (
        <div className="rounded-md border border-border/70 bg-muted/30 p-3 text-xs text-muted-foreground">
          No document details are available for this result yet.
        </div>
      )}
    </div>
  );
}
