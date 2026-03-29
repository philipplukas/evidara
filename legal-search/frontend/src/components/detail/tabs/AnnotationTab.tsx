"use client";

import { Info, MessageSquare } from "lucide-react";
import type { AnnotationViewModel } from "@/lib/types";
import { EmptySection } from "../EmptySection";

interface AnnotationTabProps {
  annotations: AnnotationViewModel[];
}

export function AnnotationTab({ annotations }: AnnotationTabProps) {
  if (annotations.length === 0) {
    return (
      <div className="p-5">
        <EmptySection label="No annotations available" />
      </div>
    );
  }

  return (
    <div className="p-5 space-y-4">
      {annotations.map((ann, i) => (
        <div key={i} className="rounded-lg border border-brand/10 bg-brand/[0.02] p-4">
          <div className="flex items-center gap-2 mb-2">
            <MessageSquare className="w-3.5 h-3.5 text-brand" />
            <p className="text-xs font-semibold text-brand">{ann.title}</p>
          </div>
          <p className="text-sm text-foreground/80 leading-relaxed mb-3 font-document">
            {ann.content}
          </p>
          <div className="flex items-center gap-4 text-micro text-muted-foreground">
            {ann.provenance && (
              <span className="flex items-center gap-1">
                <Info className="w-3 h-3" />
                {ann.provenance}
              </span>
            )}
            {ann.confidence && (
              <span className="px-1.5 py-0.5 rounded bg-green-50 text-green-700 font-medium text-tiny">
                {ann.confidence} confidence
              </span>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
