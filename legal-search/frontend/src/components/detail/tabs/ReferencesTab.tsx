"use client";

import { useTranslations } from "next-intl";
import type { ReferenceGroup } from "@/lib/types";
import { ActionTextLink, InteractiveRow, SectionLabel } from "../../primitives";
import { TabEmptyState } from "./TabEmptyState";

interface ReferencesTabProps {
  references: ReferenceGroup[];
  onFocus?: (id: string) => void;
  onPivot?: (label: string, sourceId: string) => void;
  sourceId: string;
  sourceTitle: string;
}

/**
 * Preview surface for references (incoming/outgoing).
 * "Show all" is the escape hatch → PIVOT → center panel context switch.
 */
export function ReferencesTab({
  references,
  onFocus,
  onPivot,
  sourceId,
  sourceTitle,
}: ReferencesTabProps) {
  const t = useTranslations("detail");
  if (references.length === 0) {
    return (
      <TabEmptyState
        title={t("empty.noReferencesTitle")}
        description={t("empty.noReferencesDescription")}
      />
    );
  }

  return (
    <div className="space-y-5 px-5 py-5">
      <div className="space-y-1">
        <SectionLabel>{t("tabs.references")}</SectionLabel>
        <p className="max-w-2xl text-xs leading-5 text-muted-foreground">
          {t("descriptions.references")}
        </p>
      </div>

      {references.map((group, i) => (
        <section key={i} className="space-y-2">
          <div className="flex items-center justify-between gap-3">
            <SectionLabel>
              <span>{group.direction}</span>
              <span className="rounded-full bg-muted px-1.5 py-0.5 text-tiny font-semibold text-muted-foreground">
                {group.items.length}
              </span>
            </SectionLabel>
            {onPivot && group.items.length > 0 && (
              <ActionTextLink
                onClick={() => onPivot(`${group.direction} ${sourceTitle}`, sourceId)}
                showArrow
              >
                {t("tabs.showAll")}
              </ActionTextLink>
            )}
          </div>
          <div className="space-y-1.5">
            {group.items.map((item) => (
              <InteractiveRow
                key={item.id}
                onClick={() => onFocus?.(item.id)}
                className="rounded-xl border border-border/40 bg-surface-panel/70 px-3 py-2.5 transition-all hover:border-accent-core/20 hover:bg-surface-panel hover:shadow-sm"
              >
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
              </InteractiveRow>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
