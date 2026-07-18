/**
 * `AuthorityList` — the authorities reference-data list, rendered with Tailwind +
 * `ra-core` primitives (ADR-0026). The MUI `<List>`/`<Datagrid>` version rendered
 * every authority with no total count and no reachable pages (the admin side of
 * #616, the direct twin of the jurisdictions fix). This wires `useListController`
 * → `DataTable`, which paginates and surfaces the total via the caption — the same
 * affordance Jurisdictions / Sources / the corrections queue use.
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
        render: (record) => (
          <span className="font-mono text-[12px] text-[var(--foreground-muted)]">
            {record.jurisdiction_id || "Global"}
          </span>
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
              The authority registry that sources map to. Paged for scale — use the sort headers and
              pager to move through the list.
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
