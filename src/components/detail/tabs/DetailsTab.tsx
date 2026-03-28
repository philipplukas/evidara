"use client";

import type { DetailViewModel } from "@/lib/types";
import { MetadataSection } from "../MetadataSection";

interface DetailsTabProps {
  detail: DetailViewModel;
}

export function DetailsTab({ detail }: DetailsTabProps) {
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
            // TODO: sanitize with DOMPurify before production.
            // Safe now because contentHtml comes from our own mock data / BFF.
            // The BFF renders legal article text with structural markup
            // (marginal notes, paragraph numbers) that must be preserved as HTML.
            dangerouslySetInnerHTML={{ __html: detail.contentHtml }}
          />
        </div>
      )}
    </div>
  );
}
