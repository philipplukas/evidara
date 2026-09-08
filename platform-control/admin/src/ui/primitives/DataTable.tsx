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
import { useCallback, useEffect, useRef, useState } from "react";
import { cn } from "./cn";
import {
  NO_TABLE_OVERFLOW,
  resolveTableOverflow,
  sameTableOverflow,
  type TableOverflow,
  tableOverflowState,
} from "./tableOverflow";

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
  /**
   * Pin this column to the right edge so horizontal scroll cannot take it away.
   *
   * Reserved for columns carrying the row's *actions*. On the run queue the
   * ACTIONS column holds cancel and retry — the only levers an operator has on
   * a live run — and at 1440px it sat entirely past the right edge of the
   * scroll container. A column an operator must be able to reach under pressure
   * does not get to be the one that scrolls away.
   */
  stickyRight?: boolean;
}

/**
 * Classes that pin a column to the right edge of a horizontal scroller.
 *
 * Exported because not every table in the panel can be a `DataTable` — the
 * source-versions table renders expandable diff and spec sub-rows this
 * primitive has no notion of. That table hand-rolled its own scroller and so
 * inherited none of this, which put Approve and Reject 20px past the visible
 * edge at 1280px with no cue (measured: scroller visible to x=1207, every
 * button at x=1227). Sharing the strings keeps one definition of "pinned"
 * rather than a second that drifts.
 *
 * A pinned cell needs its own opaque ground, or the columns it floats over
 * show straight through it — hence the differing backgrounds for head and body.
 */
export const STICKY_RIGHT_HEADER_CLASS =
  "sticky right-0 z-10 bg-[var(--surface-input)] border-l border-[var(--border)]";
export const STICKY_RIGHT_CELL_CLASS =
  "sticky right-0 z-10 bg-[var(--surface-panel)] border-l border-[var(--border)]";

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

  /*
   * Horizontal-overflow state. `overflow-x: auto` made the table *scrollable*;
   * it never made it *look* scrollable, so columns past the right edge were
   * indistinguishable from columns that did not exist (#M16). This drives the
   * edge fades, the caption hint, and the `data-overflow` attribute.
   */
  const scrollerRef = useRef<HTMLDivElement | null>(null);
  const [overflow, setOverflow] = useState<TableOverflow>(NO_TABLE_OVERFLOW);
  /**
   * Width of the pinned column, so the right-hand edge fade can sit beside it.
   *
   * Measured 2026-09-07 on the run queue at 1280px: the fade rendered at
   * x=1191..1231 with `z-index: auto`, entirely inside the sticky column's
   * x=1124..1231 at `z-index: 10` — so the "there is more to the right" cue was
   * painted BEHIND the very column M16 pinned, on the only table that has one.
   * Both were added in the same PR (#873) and never seen together.
   */
  const [stickyWidth, setStickyWidth] = useState(0);

  const measure = useCallback(() => {
    const element = scrollerRef.current;
    if (!element) {
      return;
    }
    const next = resolveTableOverflow({
      scrollLeft: element.scrollLeft,
      scrollWidth: element.scrollWidth,
      clientWidth: element.clientWidth,
    });
    // How wide the pinned column is, so the right-hand fade can sit BESIDE it
    // rather than under it. Read from the DOM rather than assumed: the Actions
    // column's width depends on which buttons that row set renders.
    const stickyCell = element.querySelector<HTMLElement>("thead th[data-sticky-right='true']");
    setStickyWidth(stickyCell ? Math.round(stickyCell.getBoundingClientRect().width) : 0);
    // Identity-stable when nothing changed, so the render-time measurement
    // below settles instead of looping.
    setOverflow((prev) => (sameTableOverflow(prev, next) ? prev : next));
  }, []);

  useEffect(() => {
    const element = scrollerRef.current;
    if (!element) {
      return;
    }
    measure();
    element.addEventListener("scroll", measure, { passive: true });
    // A column set can change width without the container resizing (a longer
    // failure reason, a wider id), so observe the table too — a window-resize
    // listener alone would miss it.
    const observer =
      typeof ResizeObserver === "undefined" ? null : new ResizeObserver(() => measure());
    observer?.observe(element);
    const table = element.firstElementChild;
    if (table) {
      observer?.observe(table);
    }
    return () => {
      element.removeEventListener("scroll", measure);
      observer?.disconnect();
    };
  }, [measure]);

  /*
   * Deliberately dependency-free: re-measure after *every* render.
   *
   * A render that changes column widths without resizing the container (a page
   * of runs with longer ids, a filter that drops the widest failure reason) does
   * not fire `scroll`, and `ResizeObserver` on the table catches most but not
   * all of it. Measuring on render is cheap — three reads and a `setState` that
   * no-ops when the value is unchanged — and it cannot go stale.
   */
  useEffect(measure);

  const hasStickyColumn = columns.some((col) => col.stickyRight);
  const showCaptionBand = caption != null || overflow.overflowing;

  return (
    <div className="overflow-hidden rounded-lg border border-[var(--border)] bg-[var(--surface-panel)] shadow-[var(--shadow-card)]">
      {showCaptionBand ? (
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--border)] px-5 py-3 text-[12px] font-semibold uppercase tracking-[0.08em] text-[var(--text-meta)]">
          <span>{caption}</span>
          {overflow.overflowing ? (
            /*
             * Said in words, not only in a gradient: a fade at the edge is a
             * hint a hurried operator can miss and a screen-reader user cannot
             * see at all. `hasStickyColumn` changes what is true, so it changes
             * what this claims.
             */
            <span
              className="font-normal normal-case tracking-normal text-[var(--foreground-subtle)]"
              data-testid="datatable-overflow-hint"
            >
              <span className="font-semibold">Scrolls horizontally</span>
              {hasStickyColumn
                ? " — more columns to the side; Actions stays pinned."
                : " — more columns to the side."}
            </span>
          ) : null}
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
      {/*
       * `relative` anchors the edge fades below. The fades are decoration only
       * (`aria-hidden`, `pointer-events-none`); the caption band above carries
       * the same fact in text.
       */}
      <div className="relative">
        <div
          ref={scrollerRef}
          className="overflow-x-auto"
          data-overflow={tableOverflowState(overflow)}
        >
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
                      data-sticky-right={col.stickyRight ? "true" : undefined}
                      className={cn(
                        "text-left px-4 py-3 border-b border-[var(--border)]",
                        "text-[12px] font-bold uppercase tracking-[0.08em] text-[var(--text-meta)]",
                        // A pinned header needs its own opaque ground, or the
                        // columns it floats over show straight through it.
                        col.stickyRight && STICKY_RIGHT_HEADER_CLASS,
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
                            /*
                             * `border-0 bg-transparent p-0` is load-bearing, not
                             * tidiness. `globals.css` deliberately imports only
                             * Tailwind's theme + utilities layers and skips
                             * preflight (the residual MUI pages need their base
                             * styles), so a bare <button> keeps the UA default:
                             * `border: 2px outset rgb(0,0,0)` on a grey
                             * ButtonFace ground. Every sortable header on every
                             * list rendered with that bevel, which reads as a
                             * stuck focus ring. The admin-wide reset in
                             * globals.css covers this class of bug generally;
                             * these utilities keep the primitive correct on its
                             * own terms.
                             */
                            "border-0 bg-transparent p-0 font-bold text-inherit cursor-pointer",
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
                      <td
                        key={col.key}
                        className={cn(
                          "px-4 py-3.5",
                          col.stickyRight && STICKY_RIGHT_CELL_CLASS,
                          col.className,
                        )}
                      >
                        {col.render(record)}
                      </td>
                    ))}
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/*
         * Edge fades. Decoration only — the caption band states the same fact in
         * words, because a gradient is invisible to a screen reader and easy to
         * miss under pressure. They sit outside the scroller so they stay put
         * while the content moves under them.
         */}
        {overflow.canScrollLeft ? (
          <div
            aria-hidden
            data-testid="datatable-fade-left"
            className="pointer-events-none absolute inset-y-0 left-0 w-8 bg-gradient-to-r from-[var(--surface-panel)] to-transparent"
          />
        ) : null}
        {overflow.canScrollRight ? (
          <div
            aria-hidden
            data-testid="datatable-fade-right"
            // Offset by the pinned column's width so the fade sits immediately
            // to its LEFT, over the content that is actually being cut. At
            // `right-0` it rendered underneath the pinned column (which carries
            // `z-10` and an opaque ground) and was never visible on the one
            // table that has one.
            style={{ right: stickyWidth }}
            className="pointer-events-none absolute inset-y-0 w-10 bg-gradient-to-l from-[var(--surface-panel)] to-transparent"
          />
        ) : null}
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
