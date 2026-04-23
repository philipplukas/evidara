"use client";

import { Info, MessageSquare } from "lucide-react";
import { useTranslations } from "next-intl";
import type { AnnotationViewModel } from "@/lib/types";
import { SectionLabel } from "../../primitives";
import { TabEmptyState } from "./TabEmptyState";

interface AnnotationTabProps {
  annotations: AnnotationViewModel[];
}

export function AnnotationTab({ annotations }: AnnotationTabProps) {
  const t = useTranslations("detail");
  if (annotations.length === 0) {
    return (
      <TabEmptyState
        title={t("empty.noAnnotationsTitle")}
        description={t("empty.noAnnotationsDescription")}
      />
    );
  }

  return (
    <div className="space-y-4 px-5 py-5">
      <div className="space-y-1">
        <SectionLabel>{t("tabs.annotations")}</SectionLabel>
        <p className="max-w-2xl text-xs leading-5 text-muted-foreground">
          {t("descriptions.annotations")}
        </p>
      </div>

      {annotations.map((ann, i) => (
        <div
          key={i}
          className="rounded-2xl border border-brand/10 bg-brand/[0.025] px-4 py-4 shadow-inset-surface"
        >
          <div className="flex items-start gap-3">
            <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-brand/10 text-brand">
              <MessageSquare className="h-3.5 w-3.5" />
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <p className="text-xs font-semibold text-brand">{ann.title}</p>
                {ann.sourceCount != null && (
                  <span className="rounded-full bg-brand/10 px-2 py-0.5 text-tiny font-semibold text-brand">
                    {ann.sourceCount} {t("sourcesSuffix")}
                  </span>
                )}
                {ann.confidence && (
                  <span className="rounded-full bg-status-healthy-subtle px-2 py-0.5 text-tiny font-semibold text-status-healthy">
                    {ann.confidence} {t("confidenceSuffix")}
                  </span>
                )}
              </div>
              <p className="mt-2 text-sm leading-7 text-foreground/85 font-document">
                {ann.content}
              </p>
              <div className="mt-3 flex flex-wrap items-center gap-3 text-tiny text-muted-foreground">
                {ann.provenance && (
                  <span className="inline-flex items-center gap-1">
                    <Info className="h-3 w-3" />
                    {ann.provenance}
                  </span>
                )}
              </div>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
