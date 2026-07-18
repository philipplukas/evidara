/**
 * `AuthorityList` — the authorities reference-data list, rendered with Tailwind
 * + `ra-core` primitives (ADR-0026: replaced the MUI `<List>`/`<Datagrid>`
 * scaffolding once the Tailwind primitives reached parity — the sources /
 * corrections precedents).
 *
 * Mirrors the JurisdictionList port: the MUI version had no Tailwind total
 * count and no reachable pages (the admin side of #616). This wires
 * `useListController` → `DataTable`, which paginates (`total` / `page` /
 * `perPage` / `onPageChange`) and surfaces the total via the table caption.
 * Authorities may be jurisdiction-scoped or global, so the jurisdiction column
 * renders "Global" when unset. Row-click opens the authority's edit page.
 */
"use client";

import { ListContextProvider, ResourceContextProvider, useListController } from "ra-core";
import { useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { ResourceName } from "../../domain/resourceNames";
import type { AuthorityRecord } from "../../lib/admin/dataProvider";
import { formatSwissDateTime } from "../../lib/format/date";
import { DataTable, type DataTableColumn } from "../../ui/primitives";

export function AuthorityList() {
  const controller = useListController<AuthorityRecord>({
    resource: ResourceName.Authorities,
    perPage: 50,
    sort: { field: "authority_id", order: "ASC" },
  });
  const navigate = useNavigate();

  const records = controller.data;

  const columns: DataTableColumn<AuthorityRecord>[] = useMemo(
    () => [
      {
        key: "authority",
        header: "Authority",
        sortField: "authority_id",
        render: (record) => (
          <span className="font-mono text-[12px] text-[var(--foreground)]">
            {record.authority_id}
          </span>
        ),
      },
      {
        key: "name",
        header: "Name",
        sortField: "name",
        render: (record) => (
          <span className="font-semibold text-[var(--foreground)]">{record.name}</span>
        ),
      },
      {
        key: "slug",
        header: "Slug",
        sortField: "slug",
        render: (record) => (
          <span className="font-mono text-[12px] text-[var(--foreground-muted)]">
            {record.slug}
          </span>
        ),
      },
      {
        key: "jurisdiction",
        header: "Jurisdiction",
        sortField: "jurisdiction_id",
        render: (record) =>
          record.jurisdiction_id ? (
            <span className="font-mono text-[12px] text-[var(--foreground-muted)]">
              {record.jurisdiction_id}
            </span>
          ) : (
            <span className="text-[var(--foreground-faint)]">Global</span>
          ),
      },
      {
        key: "updated",
        header: "Updated",
        sortField: "updated_at",
        render: (record) => (
          <span className="text-[var(--foreground-muted)] whitespace-nowrap">
            {formatSwissDateTime(record.updated_at) || "—"}
          </span>
        ),
      },
    ],
    [],
  );

  return (
    <ResourceContextProvider value={ResourceName.Authorities}>
      <ListContextProvider value={controller}>
        <div className="px-4 py-6 sm:px-6 sm:py-8 max-w-[var(--container-max)] mx-auto space-y-4">
          <header className="space-y-1">
            <p className="text-[11px] uppercase tracking-[0.16em] font-semibold text-[var(--foreground-subtle)]">
              Reference data
            </p>
            <h1 className="font-[family:var(--font-admin-serif)] text-[28px] font-semibold text-[var(--foreground)] leading-tight">
              Authorities
            </h1>
            <p className="text-[14px] text-[var(--foreground-muted)] max-w-[68ch]">
              The authority registry that maps sources to their publishing bodies. Paged for scale —
              use the sort headers and pager to move through the corpus.
            </p>
          </header>

          <DataTable<AuthorityRecord>
            records={records}
            columns={columns}
            getRowId={(r) => String(r.id)}
            isLoading={controller.isPending}
            error={controller.error}
            sort={controller.sort}
            onSort={(field, order) => controller.setSort({ field, order })}
            onRowClick={(r) => navigate(`/authorities/${encodeURIComponent(String(r.id))}`)}
            total={controller.total}
            page={controller.page}
            perPage={controller.perPage}
            onPageChange={controller.setPage}
            empty="No authorities."
            caption={
              controller.total !== undefined
                ? `${controller.total} authorit${controller.total === 1 ? "y" : "ies"}`
                : null
            }
          />
        </div>
      </ListContextProvider>
    </ResourceContextProvider>
  );
}
