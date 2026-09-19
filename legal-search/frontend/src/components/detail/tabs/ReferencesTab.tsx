"use client";

import { Unlink } from "lucide-react";
import { useTranslations } from "next-intl";
import type { ReferenceGroup, ReferenceItem } from "@/lib/types";
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
 * The reasons the citation graph records for a citation it could not resolve.
 *
 * Listed here so an unknown code renders as itself rather than as a
 * translation that does not exist — a code we have never seen is information,
 * and silently swallowing it would be the same class of loss as dropping the
 * reason altogether. The three come from
 * `legal-search/api/src/modules/citations/citation-resolution.ts`.
 */
const KNOWN_UNRESOLVED_REASONS = ["not_normalizable", "no_target_in_corpus", "ambiguous"] as const;

type KnownUnresolvedReason = (typeof KNOWN_UNRESOLVED_REASONS)[number];

function isKnownReason(reason: string): reason is KnownUnresolvedReason {
  return (KNOWN_UNRESOLVED_REASONS as readonly string[]).includes(reason);
}

const ROW_CLASS =
  "w-full rounded-xl border border-border/40 bg-surface-panel/70 px-3 py-2.5 text-left";

/**
 * Preview surface for references.
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

  /**
   * What a row says, resolvable or not.
   *
   * `citation` is the field the API sends. This used to read `item.subtitle`
   * — a key no response has ever carried — so every row rendered its title
   * alone and the four distinct citations on the ZH Hundegesetz read as two
   * repeated labels (#1040).
   */
  const rowBody = (item: ReferenceItem) => (
    <div className="min-w-0 flex-1">
      <div className="flex items-start gap-2">
        <span className="min-w-0 flex-1 text-xs font-medium text-foreground line-clamp-2">
          {item.title}
        </span>
        {!item.resolved && (
          <span className="inline-flex shrink-0 items-center gap-1 rounded-full bg-muted px-1.5 py-0.5 text-tiny font-semibold text-muted-foreground">
            <Unlink className="h-2.5 w-2.5" aria-hidden="true" />
            {t("references.unresolved")}
          </span>
        )}
      </div>
      {item.citation && item.citation !== item.title && (
        <div className="mt-0.5 text-micro text-muted-foreground line-clamp-2">{item.citation}</div>
      )}
      {!item.resolved && (
        <div className="mt-0.5 text-micro text-muted-foreground/80">
          {item.unresolvedReason
            ? isKnownReason(item.unresolvedReason)
              ? t(`references.reasons.${item.unresolvedReason}`)
              : item.unresolvedReason
            : t("references.reasonUnrecorded")}
        </div>
      )}
    </div>
  );

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
            {group.items.map((item) => {
              // GUARD (ADR-0052 — unknown is not zero). A citation the corpus
              // cannot answer is not a link. Every citation on the ZH
              // Hundegesetz carries `no_target_in_corpus`, and all four
              // rendered as rows identical to resolvable ones whose click
              // 404'd. The target id, not the row, decides: `resolved` is
              // false exactly when the BFF has no document to send us to.
              if (!item.resolved || !item.targetDocumentId) {
                return (
                  <div
                    key={item.id}
                    data-unresolved="true"
                    className={`${ROW_CLASS} border-dashed bg-muted/20`}
                  >
                    {rowBody(item)}
                  </div>
                );
              }

              const targetId = item.targetDocumentId;
              return (
                <InteractiveRow
                  key={item.id}
                  onClick={() => onFocus?.(targetId)}
                  className={`${ROW_CLASS} transition-all hover:border-accent-core/20 hover:bg-surface-panel hover:shadow-sm`}
                >
                  {rowBody(item)}
                </InteractiveRow>
              );
            })}
          </div>
        </section>
      ))}
    </div>
  );
}
