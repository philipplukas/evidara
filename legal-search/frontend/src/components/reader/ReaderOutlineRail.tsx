"use client";

import { List } from "lucide-react";
import { useTranslations } from "next-intl";
import { OUTLINE_INDENT_CLASS, relativeDepths } from "@/lib/document-structure";
import type { LocalStructureItem } from "@/lib/types";
import { SectionLabel } from "../primitives";

interface ReaderOutlineRailProps {
  items: LocalStructureItem[];
  /**
   * Sections `buildDocumentOutline` placed in the body. Only these are
   * clickable — a row with nowhere to scroll to must not accept a click and do
   * nothing, which is indistinguishable from a jump that worked (#1040).
   */
  anchoredIds: ReadonlySet<string>;
  /** The section the reader is currently inside, from the scroll spy. */
  activeSectionId: string | null;
  /** Move the reader to a section of the open document. Never a navigation. */
  onSelectSection: (id: string) => void;
  /** Rendered as a strip that still states the position. See `reading-layout`. */
  collapsed: boolean;
  /** Restores the rail to its listed width. Only meaningful when collapsed. */
  onExpand: () => void;
}

/**
 * The document outline, beside the text rather than instead of it.
 *
 * Before #1053 this lived behind a tab that *replaced* the body, so for the
 * ZGB's 1,377 sections, seeing where you are and reading where you are were
 * two different screens. Legal reading is non-linear — §7, out to the federal
 * act it operates under, back, §8 — and a tab cannot support that.
 *
 * Collapsed it keeps the one thing that cannot be recovered from the text
 * itself: the position. A strip that showed only an icon would make the narrow
 * window strictly worse than no rail at all.
 */
export function ReaderOutlineRail({
  items,
  anchoredIds,
  activeSectionId,
  onSelectSection,
  collapsed,
  onExpand,
}: ReaderOutlineRailProps) {
  const t = useTranslations("reader");
  const tDetail = useTranslations("detail");
  const hasOutline = items.length > 0;
  const total = items.length;
  const activeIndex = activeSectionId ? items.findIndex((item) => item.id === activeSectionId) : -1;
  const position = activeIndex >= 0 ? activeIndex + 1 : null;
  const positionText = `${position ?? "–"}/${total}`;
  const positionLabel = t("outline.position", { position: position ?? 0, total });

  if (collapsed) {
    return (
      <nav
        aria-label={t("outline.heading")}
        className="flex h-full flex-col items-center gap-3 overflow-hidden py-3"
      >
        <button
          type="button"
          onClick={onExpand}
          aria-label={t("outline.expand")}
          title={t("outline.expand")}
          className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-border/70 bg-surface-shell/45 text-muted-foreground shadow-inset-surface transition-colors hover:border-accent-core/40 hover:text-accent-core focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring"
        >
          <List className="h-4 w-4" />
        </button>
        {/* The position survives the collapse. It is the answer the body
            cannot give you by being read. A document that publishes no outline
            has no position to state, and says so rather than showing "–/0". */}
        {hasOutline && (
          <span className="shrink-0 rounded-full bg-accent-core-subtle px-1.5 py-0.5 text-tiny font-semibold tabular-nums text-accent-core">
            <span data-testid="reader-outline-position" aria-hidden="true">
              {positionText}
            </span>
            <span className="sr-only">{positionLabel}</span>
          </span>
        )}
        <span
          aria-hidden="true"
          className="select-none text-tiny font-semibold uppercase tracking-[0.16em] text-muted-foreground [writing-mode:vertical-rl]"
        >
          {t("outline.heading")}
        </span>
      </nav>
    );
  }

  const depths = relativeDepths(items);

  return (
    <nav aria-label={t("outline.heading")} className="flex h-full min-h-0 flex-col">
      <div className="flex items-center justify-between gap-2 border-b border-border/60 px-3 py-2.5">
        <SectionLabel>{t("outline.heading")}</SectionLabel>
        {hasOutline && (
          <span className="shrink-0 rounded-full bg-muted px-1.5 py-0.5 text-tiny font-semibold tabular-nums text-muted-foreground">
            <span data-testid="reader-outline-position" aria-hidden="true">
              {positionText}
            </span>
            <span className="sr-only">{positionLabel}</span>
          </span>
        )}
      </div>

      {/* Not a blank column: "this document publishes no outline" is a real
          answer and has to be stated, or the rail reads as broken. */}
      {!hasOutline && (
        <div className="p-3">
          <div className="rounded-xl border border-dashed border-border/70 bg-muted/20 px-3 py-4">
            <h3 className="text-xs font-semibold text-foreground">
              {tDetail("empty.noStructureTitle")}
            </h3>
            <p className="mt-1 text-micro leading-5 text-muted-foreground">
              {tDetail("empty.noStructureDescription")}
            </p>
          </div>
        </div>
      )}

      <ol className="m-0 min-h-0 flex-1 list-none space-y-0.5 overflow-y-auto p-2">
        {items.map((item) => {
          const depth = depths.get(item.id) ?? 0;
          const indent =
            OUTLINE_INDENT_CLASS[depth] ?? OUTLINE_INDENT_CLASS[OUTLINE_INDENT_CLASS.length - 1];
          const isActive = item.id === activeSectionId;
          const canJump = anchoredIds.has(item.id);

          const shared = `block w-full rounded-lg border-l-2 py-1.5 pe-2 text-left text-xs leading-5 ${indent}`;
          const tone = isActive
            ? "border-l-accent-core bg-accent-core-subtle font-semibold text-accent-core"
            : "border-l-transparent text-foreground/75";

          return (
            <li key={item.id}>
              {canJump ? (
                <button
                  type="button"
                  onClick={() => onSelectSection(item.id)}
                  aria-current={isActive ? "location" : undefined}
                  className={`${shared} ${tone} transition-colors ${
                    isActive ? "" : "hover:bg-muted/50 hover:text-foreground"
                  } focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring`}
                >
                  <span className="block truncate ps-2">{item.label}</span>
                </button>
              ) : (
                // Not a control: this section was not placed in the body, so
                // there is nowhere to send the reader.
                <span className={`${shared} ${tone} opacity-70`}>
                  <span className="block truncate ps-2">{item.label}</span>
                </span>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
