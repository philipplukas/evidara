/**
 * `JurisdictionList` — the jurisdictions reference-data list, rendered with
 * Tailwind + `ra-core` primitives (ADR-0026: replaced the MUI
 * `<List>`/`<Datagrid>` scaffolding once the Tailwind primitives reached
 * parity — the sources / corrections precedents).
 *
 * The MUI version rendered every jurisdiction as one long scroll with no total
 * count and no reachable pages (the admin side of #616). This wires
 * `useListController` → `DataTable`, which paginates (`total` / `page` /
 * `perPage` / `onPageChange`) and surfaces the total via the table caption —
 * the same affordance Sources and the corrections queue already use. Row-click
 * opens the jurisdiction's edit page.
 */
"use client";

import { ListContextProvider, ResourceContextProvider, useListController } from "ra-core";
import { useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { ResourceName } from "../../domain/resourceNames";
import type { JurisdictionRecord } from "../../lib/admin/dataProvider";
import { formatSwissDateTime } from "../../lib/format/date";
import { DataTable, type DataTableColumn } from "../../ui/primitives";

export function JurisdictionList() {
  const controller = useListController<JurisdictionRecord>({
    resource: ResourceName.Jurisdictions,
    perPage: 50,
    sort: { field: "jurisdiction_id", order: "ASC" },
  });
  const navigate = useNavigate();

  const records = controller.data;

  const columns: DataTableColumn<JurisdictionRecord>[] = useMemo(
    () => [
      {
        key: "jurisdiction",
        header: "Jurisdiction",
        sortField: "jurisdiction_id",
        render: (record) => (
          <span className="font-mono text-[12px] text-[var(--foreground)]">
            {record.jurisdiction_id}
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
    <ResourceContextProvider value={ResourceName.Jurisdictions}>
      <ListContextProvider value={controller}>
        <div className="px-4 py-6 sm:px-6 sm:py-8 max-w-[var(--container-max)] mx-auto space-y-4">
          <header className="space-y-1">
            <p className="text-[11px] uppercase tracking-[0.16em] font-semibold text-[var(--foreground-subtle)]">
              Reference data
            </p>
            <h1 className="font-[family:var(--font-admin-serif)] text-[28px] font-semibold text-[var(--foreground)] leading-tight">
              Jurisdictions
            </h1>
            <p className="text-[14px] text-[var(--foreground-muted)] max-w-[68ch]">
              The jurisdiction registry that anchors authorities and sources. Paged for scale — use
              the sort headers and pager to move through the corpus.
            </p>
          </header>

          <DataTable<JurisdictionRecord>
            records={records}
            columns={columns}
            getRowId={(r) => String(r.id)}
            isLoading={controller.isPending}
            error={controller.error}
            sort={controller.sort}
            onSort={(field, order) => controller.setSort({ field, order })}
            onRowClick={(r) => navigate(`/jurisdictions/${encodeURIComponent(String(r.id))}`)}
            total={controller.total}
            page={controller.page}
            perPage={controller.perPage}
            onPageChange={controller.setPage}
            empty="No jurisdictions."
            caption={
              controller.total !== undefined
                ? `${controller.total} jurisdiction${controller.total === 1 ? "" : "s"}`
                : null
            }
          />
        </div>
      </ListContextProvider>
    </ResourceContextProvider>
  );
}
