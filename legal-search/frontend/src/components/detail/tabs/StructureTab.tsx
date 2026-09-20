"use client";

import { BookOpen } from "lucide-react";
import { useTranslations } from "next-intl";
import type { KeyboardEvent } from "react";
import { relativeDepths } from "@/lib/document-structure";
import type { LocalStructureItem } from "@/lib/types";
import { SectionLabel } from "../../primitives";
import { TabEmptyState } from "./TabEmptyState";

interface StructureTabProps {
  items: LocalStructureItem[];
  /**
   * Move the reader to a section of THIS document.
   *
   * Deliberately not `onFocus`. This tab used to hand a `section_id` to the
   * workspace's document-selection callback, which passed it to
   * `getDocument(id)` — a document endpoint — so every click on the outline
   * issued `GET /v1/documents/sec_…`, took a 404 and replaced the panel with
   * "Dieses Dokument ist nicht mehr verfügbar" (#1040). A section is a place
   * inside the open document, not another document.
   */
  onSelectSection?: (id: string) => void;
  /**
   * Sections that were located in the body (`buildDocumentOutline`). Only
   * these are clickable: a row with nowhere to scroll to must not accept a
   * click and do nothing, which is indistinguishable from a jump that worked.
   */
  anchoredIds?: ReadonlySet<string>;
  /** The section the reader was last sent to. */
  activeSectionId?: string | null;
}

/** Indent per outline level. Static strings so Tailwind keeps them. */
const INDENT_CLASS = ["ps-0", "ps-4", "ps-8", "ps-12", "ps-16", "ps-20"];

export function StructureTab({
  items,
  onSelectSection,
  anchoredIds,
  activeSectionId,
}: StructureTabProps) {
  const t = useTranslations("detail");
  const handleKeyDown = (event: KeyboardEvent<HTMLButtonElement>, id: string) => {
    if (!onSelectSection) return;
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      onSelectSection(id);
    }
  };

  if (items.length === 0) {
    return (
      <TabEmptyState
        title={t("empty.noStructureTitle")}
        description={t("empty.noStructureDescription")}
      />
    );
  }

  const depths = relativeDepths(items);

  return (
    <div className="space-y-3 px-5 py-5">
      <div className="space-y-1">
        <SectionLabel>{t("tabs.localStructure")}</SectionLabel>
        <p className="max-w-2xl text-xs leading-5 text-muted-foreground">
          {t("descriptions.structure")}
        </p>
      </div>

      <div className="space-y-1">
        {items.map((item) => {
          const depth = depths.get(item.id) ?? 0;
          const indent = INDENT_CLASS[depth] ?? INDENT_CLASS[INDENT_CLASS.length - 1];
          const isActive = item.active || item.id === activeSectionId;
          const canJump = Boolean(onSelectSection && anchoredIds?.has(item.id));

          const body = (
            <>
              <BookOpen className="mt-0.5 h-3 w-3 shrink-0" />
              <span className="min-w-0 flex-1 space-y-0.5">
                <span className="block truncate font-medium">{item.label}</span>
                {/* The section's own text. Dropped twice on the way here
                    before #1040 — by the BFF mapper and then by `mapDetail` —
                    which is what made the outline a list of labels. */}
                {item.text && (
                  <span className="block line-clamp-2 text-micro font-normal leading-5 text-muted-foreground">
                    {item.text}
                  </span>
                )}
              </span>
              {isActive && (
                <span className="shrink-0 rounded-full bg-accent-core-subtle px-1.5 py-0.5 text-tiny font-semibold text-accent-core">
                  {t("tabs.current")}
                </span>
              )}
            </>
          );

          const shared = `flex w-full items-start gap-3 rounded-xl border-l-2 px-3 py-2.5 text-left text-xs ${indent}`;
          const tone = isActive
            ? "border-l-accent-core bg-accent-core-subtle text-accent-core font-semibold shadow-inset-surface"
            : "border-l-transparent text-foreground/75";

          // A row with no anchor in the body is still worth reading — it has a
          // label and its text — but it is not a control. Rendering it as a
          // button would promise a jump the reader cannot make.
          if (!canJump) {
            return (
              <div key={item.id} className={`${shared} ${tone}`}>
                {body}
              </div>
            );
          }

          return (
            <button
              type="button"
              key={item.id}
              onClick={() => onSelectSection?.(item.id)}
              onKeyDown={(event) => handleKeyDown(event, item.id)}
              aria-current={isActive ? "location" : undefined}
              className={`${shared} transition-all ${
                isActive ? tone : `${tone} hover:bg-muted/50 hover:text-foreground`
              }`}
            >
              {body}
            </button>
          );
        })}
      </div>
    </div>
  );
}
