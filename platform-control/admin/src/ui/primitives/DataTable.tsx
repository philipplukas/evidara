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
  onRowClick?: (record: T) => void;
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
    <div className="rounded-[18px] border border-[rgba(29,41,61,0.08)] bg-white/85 shadow-[var(--shadow-card)] backdrop-blur-[12px] overflow-hidden">
      {caption ? (
        <div className="px-5 py-3 border-b border-[rgba(29,41,61,0.06)] text-[12px] uppercase tracking-[0.08em] text-[rgba(29,41,61,0.6)] font-semibold">
          {caption}
        </div>
      ) : null}

      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-sm text-[var(--foreground)]">
          <thead>
            <tr className="bg-[rgba(244,239,231,0.72)]">
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
                      "text-left px-4 py-3 border-b border-[rgba(29,41,61,0.08)]",
                      "text-[12px] font-bold uppercase tracking-[0.08em] text-[rgba(29,41,61,0.7)]",
                      canSort && "cursor-pointer select-none hover:text-[var(--foreground)]",
                      col.headerClassName,
                    )}
                    onClick={
                      canSort
                        ? () => {
                            const nextOrder: SortOrder =
                              isSorted && sort?.order === "ASC" ? "DESC" : "ASC";
                            onSort!(col.sortField!, nextOrder);
                          }
                        : undefined
                    }
                    aria-sort={
                      isSorted ? (sort!.order === "ASC" ? "ascending" : "descending") : "none"
                    }
                  >
                    <span className="inline-flex items-center gap-1">
                      {col.header}
                      {canSort ? (
                        <SortIcon
                          size={12}
                          strokeWidth={2.5}
                          className={cn(
                            "transition-opacity",
                            isSorted ? "opacity-100" : "opacity-40",
                          )}
                          aria-hidden
                        />
                      ) : null}
                    </span>
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
                  className="px-4 py-10 text-center text-[rgba(29,41,61,0.6)]"
                >
                  Loading…
                </td>
              </tr>
            ) : error ? (
              <tr>
                <td colSpan={columns.length} className="px-4 py-10 text-center text-[#b71c1c]">
                  Failed to load records.
                </td>
              </tr>
            ) : !hasRows ? (
              <tr>
                <td
                  colSpan={columns.length}
                  className="px-4 py-10 text-center text-[rgba(29,41,61,0.6)]"
                >
                  {empty ?? "No records."}
                </td>
              </tr>
            ) : (
              records!.map((record) => (
                <tr
                  key={getRowId(record)}
                  onClick={onRowClick ? () => onRowClick(record) : undefined}
                  className={cn(
                    "border-b border-[rgba(29,41,61,0.06)] last:border-b-0 align-top",
                    onRowClick && "cursor-pointer hover:bg-[var(--brand-wash-4)]",
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
        <div className="flex items-center justify-between px-5 py-3 border-t border-[rgba(29,41,61,0.06)] text-[12px] text-[rgba(29,41,61,0.7)]">
          <span>
            Page {page} of {totalPages} · {total} total
          </span>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => onPageChange(Math.max(1, page - 1))}
              disabled={page <= 1}
              className="px-3 h-8 rounded-full border border-[var(--border)] bg-white/70 disabled:opacity-40 hover:bg-white"
            >
              Previous
            </button>
            <button
              type="button"
              onClick={() => onPageChange(Math.min(totalPages, page + 1))}
              disabled={page >= totalPages}
              className="px-3 h-8 rounded-full border border-[var(--border)] bg-white/70 disabled:opacity-40 hover:bg-white"
            >
              Next
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
