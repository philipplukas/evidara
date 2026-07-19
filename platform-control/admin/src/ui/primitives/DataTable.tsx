/**
 * `DataTable` — generic data table bound to `ra-core`'s `useListController`.
 *
 * Consumers pass `records`, `columns`, `getRowId`, and the controller's
 * `sort` / `setSort` / `page` / `setPage` / `total` — the table stays
 * headless of any specific resource. Sort headers render chevrons based on
 * the active sort field; `onRowClick` wires routing.
 *
 * Not yet modelled (follow-up increments):
 *   - bulk row selection (`selectedIds` / `onToggleItem`)
 *   - inline filter row
 *   - column resize / hide
 *   - virtualisation
 */
"use client";

import { ChevronDown, ChevronsUpDown, ChevronUp } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "./cn";

export type SortOrder = "ASC" | "DESC";

export interface DataTableColumn<T> {
  key: string;
  header: string;
  /** Backend sort field. When omitted, the column is non-sortable. */
  sortField?: string;
  render: (record: T) => ReactNode;
  /** Extra classes for the <td>. */
  className?: string;
  /** Extra classes for the <th>. */
  headerClassName?: string;
}

export interface DataTableProps<T> {
  records: T[] | undefined;
  columns: DataTableColumn<T>[];
  getRowId: (record: T) => string;
  isLoading?: boolean;
  error?: unknown;
  sort?: { field: string; order: SortOrder };
  /**
   * Fires with the column's `sortField`. Caller is responsible for toggling
   * ASC/DESC (matches ra-core's `setSort` semantics).
   */
  onSort?: (field: string, order: SortOrder) => void;
  /**
   * Activating a row. Wired to pointer click *and* keyboard (Enter / Space) —
   * on the canonical v2 pages this is the only path to a record's detail, so a
   * mouse-only handler locked keyboard operators out of every record (#624).
   */
  onRowClick?: (record: T) => void;
  /**
   * Accessible name for an activatable row, e.g. `(r) => \`Open run ${r.run_id}\``.
   * Optional: without it a focused row is announced by its cell contents.
   */
  getRowLabel?: (record: T) => string;
  total?: number;
  page?: number;
  perPage?: number;
  onPageChange?: (page: number) => void;
  empty?: ReactNode;
  caption?: ReactNode;
}

export function DataTable<T>({
  records,
  columns,
  getRowId,
  isLoading,
  error,
  sort,
  onSort,
  onRowClick,
  getRowLabel,
  total,
  page,
  perPage,
  onPageChange,
  empty,
  caption,
}: DataTableProps<T>) {
  const hasRows = !!records && records.length > 0;
  const totalPages = total && perPage ? Math.max(1, Math.ceil(total / perPage)) : undefined;

  return (
    <div className="overflow-hidden rounded-lg border border-[var(--border)] bg-[var(--surface-panel)] shadow-[var(--shadow-card)]">
      {caption ? (
        <div className="border-b border-[var(--border)] px-5 py-3 text-[12px] font-semibold uppercase tracking-[0.08em] text-[var(--text-meta)]">
          {caption}
        </div>
      ) : null}

      {/*
       * Horizontal-scroll container. Wide tables (the run queue carries 8
       * columns) must scroll *inside their own card* rather than clipping at
       * the shell's `overflow-x-hidden` main or pushing the page body wider —
       * see AGENTS.md / CLAUDE.md ("wide content scrolls in its own
       * overflow-x: auto container"). Pairs with `min-w-full` on the table
       * below: the table grows to its natural content width and this element
       * scrolls; it does not squeeze columns to fit and clip the rightmost
       * one.
       */}
      <div className="overflow-x-auto">
        {/*
         * `aria-busy` rides on the persistent <table> rather than the loading
         * cell: a live region has to exist before its content changes to be
         * announced reliably, and the cell mounts and unmounts with the state
         * it would describe. Toggling an attribute on an element that never
         * leaves the DOM is the signal assistive tech can actually observe.
         *
         * `min-w-full` (not `w-full`): fill the container when the columns are
         * narrow, but grow past it when they are not — the parent scrolls
         * instead of cramming every column into 100% width and clipping.
         */}
        <table
          aria-busy={!!isLoading}
          className="min-w-full border-collapse text-sm text-[var(--foreground)]"
        >
          <thead>
            <tr className="bg-[var(--surface-input)]">
              {columns.map((col) => {
                const isSorted = sort && col.sortField && sort.field === col.sortField;
                const canSort = !!col.sortField && !!onSort;
                const SortIcon = !isSorted
                  ? ChevronsUpDown
                  : sort.order === "ASC"
                    ? ChevronUp
                    : ChevronDown;
                return (
                  <th
                    key={col.key}
                    scope="col"
                    className={cn(
                      "text-left px-4 py-3 border-b border-[var(--border)]",
                      "text-[12px] font-bold uppercase tracking-[0.08em] text-[var(--text-meta)]",
                      col.headerClassName,
                    )}
                    aria-sort={
                      isSorted ? (sort!.order === "ASC" ? "ascending" : "descending") : "none"
                    }
                  >
                    {/*
                     * A sortable header is a real <button>, not an onClick on
                     * the <th> — the bare handler was mouse-only for the same
                     * reason the rows were (#624).
                     */}
                    {canSort ? (
                      <button
                        type="button"
                        onClick={() => {
                          const nextOrder: SortOrder =
                            isSorted && sort?.order === "ASC" ? "DESC" : "ASC";
                          onSort!(col.sortField!, nextOrder);
                        }}
                        className={cn(
                          "inline-flex items-center gap-1 select-none uppercase tracking-[0.08em]",
                          "hover:text-[var(--accent-core)]",
                          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus-ring)] rounded-sm",
                        )}
                      >
                        {col.header}
                        <SortIcon
                          size={12}
                          strokeWidth={2.5}
                          className={cn(
                            "transition-opacity",
                            isSorted ? "opacity-100" : "opacity-40",
                          )}
                          aria-hidden
                        />
                      </button>
                    ) : (
                      <span className="inline-flex items-center gap-1">{col.header}</span>
                    )}
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {isLoading && !hasRows ? (
              <tr>
                <td
                  colSpan={columns.length}
                  className="px-4 py-10 text-center text-[var(--text-meta)]"
                >
                  Loading…
                </td>
              </tr>
            ) : error ? (
              <tr>
                <td
                  colSpan={columns.length}
                  className="px-4 py-10 text-center text-[var(--status-critical)]"
                >
                  {/* `alert` announces on insertion, which is exactly how this
                      node arrives — no persistent region needed. */}
                  <span role="alert">Failed to load records.</span>
                </td>
              </tr>
            ) : !hasRows ? (
              <tr>
                <td
                  colSpan={columns.length}
                  className="px-4 py-10 text-center text-[var(--text-meta)]"
                >
                  {empty ?? "No records."}
                </td>
              </tr>
            ) : (
              records!.map((record) => (
                /*
                 * An activatable row is a real tab stop: `tabIndex={0}` plus an
                 * Enter/Space handler, because `onClick` on a <tr> never fires
                 * from the keyboard (#624). Space is `preventDefault`ed so it
                 * activates the row instead of scrolling the page.
                 *
                 * The `<tr>` deliberately keeps its implicit `row` role rather
                 * than taking `role="button"` — overriding it would strip the
                 * row/cell relationship from every cell inside and make the
                 * table harder to navigate than it is today. The stronger fix,
                 * a real <a> in the first cell (which also buys middle-click
                 * and open-in-new-tab), needs an href at each call site.
                 */
                <tr
                  key={getRowId(record)}
                  tabIndex={onRowClick ? 0 : undefined}
                  aria-label={onRowClick && getRowLabel ? getRowLabel(record) : undefined}
                  onClick={onRowClick ? () => onRowClick(record) : undefined}
                  onKeyDown={
                    onRowClick
                      ? (event) => {
                          if (event.key !== "Enter" && event.key !== " ") {
                            return;
                          }
                          // Let controls inside a cell keep their own keys.
                          if (event.target !== event.currentTarget) {
                            return;
                          }
                          event.preventDefault();
                          onRowClick(record);
                        }
                      : undefined
                  }
                  className={cn(
                    "border-b border-[var(--border)] last:border-b-0 align-top",
                    onRowClick && "cursor-pointer hover:bg-[var(--interactive-accent-subtle)]",
                    onRowClick &&
                      "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[var(--focus-ring)]",
                  )}
                >
                  {columns.map((col) => (
                    <td key={col.key} className={cn("px-4 py-3.5", col.className)}>
                      {col.render(record)}
                    </td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {totalPages && totalPages > 1 && onPageChange && page !== undefined ? (
        <div className="flex items-center justify-between border-t border-[var(--border)] px-5 py-3 text-[12px] text-[var(--text-meta)]">
          <span>
            Page {page} of {totalPages} · {total} total
          </span>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => onPageChange(Math.max(1, page - 1))}
              disabled={page <= 1}
              className="h-8 rounded-lg border border-[var(--border)] bg-[var(--surface-panel)] px-3 transition-colors hover:border-[var(--accent-core)]/30 hover:bg-[var(--surface-input)] disabled:opacity-40"
            >
              Previous
            </button>
            <button
              type="button"
              onClick={() => onPageChange(Math.min(totalPages, page + 1))}
              disabled={page >= totalPages}
              className="h-8 rounded-lg border border-[var(--border)] bg-[var(--surface-panel)] px-3 transition-colors hover:border-[var(--accent-core)]/30 hover:bg-[var(--surface-input)] disabled:opacity-40"
            >
              Next
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
