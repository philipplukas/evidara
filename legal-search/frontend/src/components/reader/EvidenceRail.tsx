"use client";

import { ChevronRight, Link2 } from "lucide-react";
import { useTranslations } from "next-intl";
import type { DetailViewModel } from "@/lib/types";
import { ReferenceGroupList } from "../detail/ReferenceGroupList";
import { SectionLabel } from "../primitives";

interface EvidenceRailProps {
  detail: DetailViewModel;
  onFocus?: (id: string) => void;
  /** Rendered as a strip that states how many references there are. */
  collapsed: boolean;
  /** Restores the rail to its listed width. Only meaningful when collapsed. */
  onExpand: () => void;
}

/**
 * What stands behind the text: where the document sits, and what it points at.
 *
 * ADR-0033 calls the citation graph "the least glamorous item here and the most
 * differentiating". The corpus holds 8,253 citations and 896 targets, and
 * before #1053 no screen rendered them beside the text they belong to — they
 * were behind a tab that replaced the document.
 *
 * ## What is deliberately NOT here
 *
 * **Incoming references (`zitiert von`).** The reverse-citation endpoints exist
 * with zero call sites (#912), so this rail has no producer for them and ships
 * the section ABSENT rather than empty. A rendered "Zitiert von (0)" would read
 * as "no norm cites this one", which is a claim the corpus cannot currently
 * make — the exact declared-and-empty defect AGENTS.md flags and the one
 * #958 exists to close.
 *
 * The governing norm is reachable here as an outgoing reference — for the ZH
 * Hundegesetz that is the federal Tierschutzgesetz, in the `SR` group — and the
 * document's placement in its collection is the `Einordnung` block. Neither is
 * a separate "superordinate" edge, because nothing in the pipeline emits one.
 */
export function EvidenceRail({ detail, onFocus, collapsed, onExpand }: EvidenceRailProps) {
  const t = useTranslations("reader");
  const tDetail = useTranslations("detail");

  const referenceCount = detail.references.reduce((sum, group) => sum + group.items.length, 0);
  const placement = detail.breadcrumbs;

  if (collapsed) {
    return (
      <aside
        aria-label={t("evidence.heading")}
        className="flex h-full flex-col items-center gap-3 overflow-hidden py-3"
      >
        <button
          type="button"
          onClick={onExpand}
          aria-label={t("evidence.expand")}
          title={t("evidence.expand")}
          className="relative inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-border/70 bg-surface-shell/45 text-muted-foreground shadow-inset-surface transition-colors hover:border-accent-core/40 hover:text-accent-core focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring"
        >
          <Link2 className="h-4 w-4" />
          {referenceCount > 0 && (
            <span className="absolute -right-1 -top-1 inline-flex h-4 min-w-4 items-center justify-center rounded-full bg-accent-core px-1 text-tiny font-semibold text-white">
              {referenceCount}
            </span>
          )}
        </button>
        <span
          aria-hidden="true"
          className="select-none text-tiny font-semibold uppercase tracking-[0.16em] text-muted-foreground [writing-mode:vertical-rl]"
        >
          {t("evidence.heading")}
        </span>
      </aside>
    );
  }

  return (
    <aside aria-label={t("evidence.heading")} className="flex h-full min-h-0 flex-col">
      <div className="border-b border-border/60 px-3 py-2.5">
        <SectionLabel>{t("evidence.heading")}</SectionLabel>
      </div>

      <div className="min-h-0 flex-1 space-y-5 overflow-y-auto px-3 py-4">
        {/* Where the document sits in the collection that publishes it. Omitted
            entirely when the source states no structural path — an empty
            breadcrumb trail is not a document at the root. */}
        {placement.length > 0 && (
          <section className="space-y-2">
            <SectionLabel>{t("evidence.placementHeading")}</SectionLabel>
            <ol className="m-0 list-none space-y-1 p-0">
              {placement.map((step, index) => (
                <li
                  key={`${step}-${index}`}
                  className="flex items-start gap-1 text-micro leading-5 text-muted-foreground"
                  style={{ paddingInlineStart: `${index * 0.5}rem` }}
                >
                  {index > 0 && (
                    <ChevronRight className="mt-0.5 h-2.5 w-2.5 shrink-0" aria-hidden="true" />
                  )}
                  <span
                    className={
                      index === placement.length - 1 ? "font-medium text-foreground/80" : undefined
                    }
                  >
                    {step}
                  </span>
                </li>
              ))}
            </ol>
          </section>
        )}

        {detail.references.length > 0 ? (
          <div className="space-y-4">
            <SectionLabel>{tDetail("tabs.references")}</SectionLabel>
            <ReferenceGroupList
              references={detail.references}
              onFocus={onFocus}
              sourceId={detail.id}
              sourceTitle={detail.title}
            />
          </div>
        ) : (
          <div className="rounded-xl border border-dashed border-border/70 bg-muted/20 px-3 py-4">
            <h3 className="text-xs font-semibold text-foreground">
              {tDetail("empty.noReferencesTitle")}
            </h3>
            <p className="mt-1 text-micro leading-5 text-muted-foreground">
              {tDetail("empty.noReferencesDescription")}
            </p>
          </div>
        )}
      </div>
    </aside>
  );
}
