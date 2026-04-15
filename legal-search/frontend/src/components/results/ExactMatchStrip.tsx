"use client";

import { Globe, Zap } from "lucide-react";
import { useTranslations } from "next-intl";
import { getIcon } from "@/lib/icons";
import type { SearchResultViewModel } from "@/lib/types";
import { Badge } from "../primitives";

interface ExactMatchStripProps {
  matches: SearchResultViewModel[];
  onSelect: (id: string) => void;
}

export function ExactMatchStrip({ matches, onSelect }: ExactMatchStripProps) {
  const t = useTranslations("results.exactMatches");
  if (matches.length === 0) return null;

  return (
    <div className="mb-4 rounded-xl border border-brand/15 bg-brand/[0.04] px-4 py-3 shadow-[inset_0_1px_0_rgba(255,255,255,0.55)]">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <Zap className="h-3.5 w-3.5 text-brand" />
            <span className="text-xs font-semibold text-brand">{t("title")}</span>
            <span className="inline-flex items-center rounded-full border border-brand/15 bg-brand/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.16em] text-brand">
              {t("confidence")}
            </span>
          </div>
          <p className="mt-1 text-[11px] leading-relaxed text-muted-foreground">
            {t("description")}
          </p>
        </div>
        <span className="shrink-0 rounded-full border border-border/60 bg-surface-panel/90 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
          {t("found", { count: matches.length })}
        </span>
      </div>
      <div className="grid gap-2 sm:grid-cols-2">
        {matches.map((match) => {
          const badge = match.badges[0];
          const icon = badge?.iconKey ? getIcon(badge.iconKey) : null;
          return (
            <button
              type="button"
              key={match.id}
              onClick={() => onSelect(match.id)}
              aria-label={t("openLabel", { title: match.title })}
              className="flex w-full items-start gap-3 rounded-lg border border-border bg-surface-panel px-3 py-2.5
                text-left transition-all hover:-translate-y-px hover:border-brand/30 hover:shadow-sm"
            >
              <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-brand/10 text-brand">
                {icon ? <span className="text-sm">{icon}</span> : <Zap className="h-3.5 w-3.5" />}
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-1.5">
                  <div className="truncate text-sm font-semibold text-foreground">
                    {match.title}
                  </div>
                  {badge && <Badge label={badge.label} colorKey={badge.colorKey} size="xs" />}
                </div>
                <div className="mt-0.5 truncate text-xs text-muted-foreground">
                  {match.subtitle}
                </div>
                {match.structuralContext && (
                  <div className="mt-1 truncate text-[11px] font-medium text-muted-foreground/75">
                    {match.structuralContext}
                  </div>
                )}
                {match.contentLanguage?.isTranslation && (
                  <div className="mt-1 inline-flex items-center gap-1 rounded-full bg-attention-subtle px-1.5 py-0.5 text-[10px] font-medium text-attention">
                    <Globe className="h-2.5 w-2.5" />
                    {match.contentLanguage.label ?? t("translatedFallback")}
                  </div>
                )}
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
