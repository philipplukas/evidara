"use client";

import { MessageSquare, Info } from "lucide-react";
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
        <div
          key={i}
          className="rounded-lg border border-[#2563eb]/10 bg-[#2563eb]/[0.02] p-4"
        >
          <div className="flex items-center gap-2 mb-2">
            <MessageSquare className="w-3.5 h-3.5 text-[#2563eb]" />
            <h4 className="text-xs font-semibold text-[#2563eb]">
              {ann.title}
            </h4>
          </div>
          <p
            className="text-sm text-foreground/80 leading-relaxed mb-3"
            style={{ fontFamily: "'Source Serif 4', 'Georgia', serif" }}
          >
            {ann.content}
          </p>
          <div className="flex items-center gap-4 text-[11px] text-muted-foreground">
            {ann.provenance && (
              <span className="flex items-center gap-1">
                <Info className="w-3 h-3" />
                {ann.provenance}
              </span>
            )}
            {ann.confidence && (
              <span className="px-1.5 py-0.5 rounded bg-green-50 text-green-700 font-medium text-[10px]">
                {ann.confidence} confidence
              </span>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
