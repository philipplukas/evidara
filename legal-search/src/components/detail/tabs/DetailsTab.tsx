"use client";

import type { DetailViewModel } from "@/lib/types";
import { SectionLabel } from "../../primitives";

interface DetailsTabProps {
  detail: DetailViewModel;
}

export function DetailsTab({ detail }: DetailsTabProps) {
  return (
    <div className="p-5 space-y-5">
      {/* Metadata */}
      {detail.metadata.length > 0 && (
        <div className="space-y-2">
          <SectionLabel>Metadata</SectionLabel>
          <div className="space-y-1.5">
            {detail.metadata.map((row, i) => (
              <div key={i} className="flex items-baseline gap-2 text-xs">
                <span className="text-muted-foreground w-28 shrink-0 font-medium">{row.label}</span>
                <span className="text-foreground/80 flex items-center gap-1">{row.value}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Content */}
      {detail.contentHtml && (
        <div className="space-y-2">
          <SectionLabel>Content</SectionLabel>
          {/* TODO: sanitize with DOMPurify before production.
              Safe now because contentHtml comes from our own mock data / BFF. */}
          <div
            className="text-sm leading-relaxed text-foreground/85 prose-sm font-document
              [&_.article-marginal]:text-micro [&_.article-marginal]:font-semibold [&_.article-marginal]:text-muted-foreground
              [&_.article-marginal]:mt-3 [&_.article-marginal]:mb-1
              [&_strong]:text-foreground [&_strong]:font-semibold
              [&_h4]:text-xs [&_h4]:font-semibold [&_h4]:uppercase [&_h4]:tracking-wider [&_h4]:text-muted-foreground [&_h4]:mt-4 [&_h4]:mb-2
              [&_p]:mb-2"
            dangerouslySetInnerHTML={{ __html: detail.contentHtml }}
          />
        </div>
      )}
    </div>
  );
}
