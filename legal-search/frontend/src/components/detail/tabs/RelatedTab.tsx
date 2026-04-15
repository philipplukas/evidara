"use client";

import { ExternalLink } from "lucide-react";
import { useTranslations } from "next-intl";
import type { RelatedGroup } from "@/lib/types";
import { ActionTextLink, Badge, InteractiveRow, SectionLabel } from "../../primitives";
import { TabEmptyState } from "./TabEmptyState";

interface RelatedTabProps {
  groups: RelatedGroup[];
  onFocus?: (id: string) => void;
  onPivot?: (label: string, sourceId: string) => void;
  sourceId: string;
}

/**
 * Preview surface for related items.
 *
 * Design rule: this is NOT a mini result system.
 * It must not grow its own filters, sorting, or deep navigation.
 * "Show all" is the escape hatch → PIVOT → center panel context switch.
 */
export function RelatedTab({ groups, onFocus, onPivot, sourceId }: RelatedTabProps) {
  const t = useTranslations("detail");
  if (groups.length === 0) {
    return (
      <TabEmptyState
        title={t("empty.noRelatedTitle")}
        description={t("empty.noRelatedDescription")}
      />
    );
  }

  return (
    <div className="space-y-5 px-5 py-5">
      <div className="space-y-1">
        <SectionLabel>{t("tabs.relatedMaterials")}</SectionLabel>
        <p className="max-w-2xl text-xs leading-5 text-muted-foreground">
          {t("descriptions.related")}
        </p>
      </div>

      {groups.map((group, i) => (
        <section key={i} className="space-y-2">
          <div className="flex items-center justify-between gap-3">
            <SectionLabel className="flex items-center gap-1.5">
              <span>{group.groupLabel}</span>
              <span className="rounded-full bg-muted px-1.5 py-0.5 text-tiny font-semibold text-muted-foreground">
                {group.items.length}
              </span>
            </SectionLabel>
            {onPivot && group.items.length > 0 && (
              <ActionTextLink onClick={() => onPivot(group.groupLabel, sourceId)} showArrow>
                {t("tabs.showAll")}
              </ActionTextLink>
            )}
          </div>
          <div className="space-y-1.5">
            {group.items.map((item) => (
              <InteractiveRow
                key={item.id}
                onClick={() => onFocus?.(item.id)}
                className="group rounded-xl border border-border/40 bg-surface-panel/70 px-3 py-2.5 transition-all hover:border-brand/20 hover:bg-surface-panel hover:shadow-sm"
              >
                {item.badge && (
                  <Badge label={item.badge.label} colorKey={item.badge.colorKey} size="xs" />
                )}
                <div className="flex-1 min-w-0">
                  <div className="text-xs font-medium text-foreground line-clamp-2">
                    {item.title}
                  </div>
                  {item.subtitle && (
                    <div className="mt-0.5 text-micro text-muted-foreground line-clamp-2">
                      {item.subtitle}
                    </div>
                  )}
                </div>
                <ExternalLink className="w-3 h-3 text-muted-foreground/30 group-hover:text-brand transition-colors shrink-0" />
              </InteractiveRow>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
