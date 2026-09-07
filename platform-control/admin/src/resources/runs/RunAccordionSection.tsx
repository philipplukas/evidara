/**
 * The accordion wrapper shared by every run-detail stage section.
 *
 * A section is now: a columns module + one `<RunAccordionSection>` in the root.
 */
"use client";

import type { Identifier } from "ra-core";
import type { ReactNode } from "react";
import {
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
  DataTable,
  type DataTableColumn,
  InlineAlert,
  Pill,
} from "../../ui/primitives";

export interface RunSectionProps<TRecord extends { id: Identifier }> {
  value: string;
  /** DOM id used as an in-page scroll target for the pipeline jump links. */
  sectionId?: string;
  title: string;
  description: string;
  /**
   * What this section cannot tell you, rendered above the rows.
   *
   * Not decoration: a section whose rows are honest but whose *absence of rows*
   * is not (the DI stage cannot see a quarantine at all) has to say so where the
   * rows are, not in a doc comment.
   */
  caveat?: ReactNode;
  rows: TRecord[] | undefined;
  /**
   * How many rows exist on the server, when that differs from how many were
   * fetched.
   *
   * The pill used to report `rows.length` alone, which is the PAGE SIZE
   * (`LIST_PARAMS.perPage` is 50). On a run with 944 captured resources the
   * metric band read "Captured 944" and the section header, immediately below
   * it, read "50 rows" — one screen stating two numbers for one quantity.
   *
   * `Pipeline Stages` in the same file already got this right ("1 of 887
   * documents timed"); this brings the rest into line.
   */
  total?: number;
  isPending: boolean;
  error: unknown;
  emptyMessage: string;
  columns: DataTableColumn<TRecord>[];
  getRowId: (record: TRecord) => string;
}

export function RunAccordionSection<TRecord extends { id: Identifier }>({
  value,
  sectionId,
  title,
  description,
  caveat,
  rows,
  total,
  isPending,
  error,
  emptyMessage,
  columns,
  getRowId,
}: RunSectionProps<TRecord>) {
  const count = rows?.length ?? 0;
  // Only says "of N" when N is genuinely larger. A section that fetched
  // everything should read "3 rows", not "3 of 3 rows".
  const label =
    total != null && total > count
      ? `${count} of ${total} rows`
      : `${count} ${count === 1 ? "row" : "rows"}`;
  return (
    <AccordionItem value={value} id={sectionId}>
      <AccordionTrigger>
        <span className="text-[15px] font-semibold text-[var(--foreground)]">{title}</span>
        {isPending ? (
          <Pill variant="meta">Loading…</Pill>
        ) : error ? (
          <Pill level="critical">Error</Pill>
        ) : (
          <Pill variant="meta">{label}</Pill>
        )}
      </AccordionTrigger>
      <AccordionContent>
        <div className="space-y-3">
          <p className="text-[13px] text-[var(--foreground-subtle)]">{description}</p>

          {caveat ? <InlineAlert tone="warning">{caveat}</InlineAlert> : null}

          {isPending ? (
            <p className="text-[13px] text-[var(--foreground-subtle)]">
              Loading {title.toLowerCase()}…
            </p>
          ) : error ? (
            <div
              role="alert"
              className="rounded-[12px] border border-[var(--status-critical)]/40 bg-[var(--status-critical-subtle)] p-3 text-[13px] text-[var(--status-critical)]"
            >
              {error instanceof Error ? error.message : `Unable to load ${title.toLowerCase()}.`}
            </div>
          ) : count === 0 ? (
            <p className="text-[13px] text-[var(--foreground-subtle)]">{emptyMessage}</p>
          ) : (
            <DataTable<TRecord>
              records={rows}
              columns={columns}
              getRowId={getRowId}
              isLoading={false}
            />
          )}
        </div>
      </AccordionContent>
    </AccordionItem>
  );
}

// ---------------------------------------------------------------------------
// Column definitions — 1:1 with v1 (labels, order, renderers).
// ---------------------------------------------------------------------------
