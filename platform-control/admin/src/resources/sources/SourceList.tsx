/**
 * `SourceList` — the sources list, rendered with Tailwind + `ra-core`
 * primitives from `src/ui/primitives/`. Wired via `<Resource list>` at
 * `/sources` (ADR-0026: the Tailwind port replaced the retired MUI list once
 * it reached parity — see #501).
 *
 *   - `useListController` drives list-page behaviour (sort, pagination,
 *     loading, error).
 *   - `useGetMany` dedupes jurisdiction / authority reference lookups the
 *     same way `<ReferenceField>` does, without forcing MUI-rendered cells.
 *   - Row-click navigates to the source detail page (`/sources/:id/show`).
 */
"use client";

import {
  ListContextProvider,
  ResourceContextProvider,
  useGetMany,
  useListController,
} from "ra-core";
import { useMemo } from "react";
import { useNavigate } from "react-router-dom";
import type {
  AuthorityRecord,
  JurisdictionRecord,
  SourceRecord,
} from "../../lib/admin/dataProvider";
import { formatSwissDateTime } from "../../lib/format/date";
import { DataTable, type DataTableColumn, Pill } from "../../ui/primitives";
import { sourceStatusToLevel } from "../shared/statusLevels";

const SOURCE_STATUS_LABEL: Record<SourceRecord["status"], string> = {
  active: "Active",
  inactive: "Inactive",
  archived: "Archived",
};

function uniqueIds(values: Array<string | null | undefined>): string[] {
  const seen = new Set<string>();
  for (const v of values) {
    if (v) seen.add(v);
  }
  return Array.from(seen);
}

export default function SourceList() {
  const controller = useListController<SourceRecord>({
    resource: "sources",
    perPage: 50,
    sort: { field: "updated_at", order: "DESC" },
  });
  const navigate = useNavigate();

  const records = controller.data;
  const jurisdictionIds = useMemo(
    () => uniqueIds(records?.map((r) => r.jurisdiction_id) ?? []),
    [records],
  );
  const authorityIds = useMemo(
    () => uniqueIds(records?.map((r) => r.authority_id) ?? []),
    [records],
  );

  // `useGetMany` dedupes + caches — same mechanism `<ReferenceField>` uses
  // internally. Empty-ids short-circuit avoids a no-op request.
  const { data: jurisdictions } = useGetMany<JurisdictionRecord>(
    "jurisdictions",
    { ids: jurisdictionIds },
    { enabled: jurisdictionIds.length > 0 },
  );
  const { data: authorities } = useGetMany<AuthorityRecord>(
    "authorities",
    { ids: authorityIds },
    { enabled: authorityIds.length > 0 },
  );

  const jurisdictionById = useMemo(() => {
    const map = new Map<string, JurisdictionRecord>();
    for (const j of jurisdictions ?? []) map.set(String(j.id), j);
    return map;
  }, [jurisdictions]);
  const authorityById = useMemo(() => {
    const map = new Map<string, AuthorityRecord>();
    for (const a of authorities ?? []) map.set(String(a.id), a);
    return map;
  }, [authorities]);

  const columns: DataTableColumn<SourceRecord>[] = [
    {
      key: "source",
      header: "Source",
      sortField: "name",
      render: (record) => (
        <div className="flex flex-col gap-0.5">
          <span className="font-semibold text-[var(--foreground)]">{record.name}</span>
          <span className="text-[12px] text-[var(--foreground-subtle)]">{record.source_id}</span>
        </div>
      ),
    },
    {
      key: "lifecycle",
      header: "Lifecycle",
      render: (record) => (
        <div className="flex flex-wrap items-center gap-1.5">
          <Pill level={sourceStatusToLevel(record.status)}>
            {SOURCE_STATUS_LABEL[record.status]}
          </Pill>
          <Pill variant="meta">{record.source_type}</Pill>
        </div>
      ),
    },
    {
      key: "jurisdiction",
      header: "Jurisdiction",
      render: (record) => {
        const j = jurisdictionById.get(record.jurisdiction_id);
        return j ? (
          <span>
            {j.name} <span className="text-[var(--foreground-subtle)]">({j.slug})</span>
          </span>
        ) : (
          <span className="text-[var(--foreground-faint)]">—</span>
        );
      },
    },
    {
      key: "authority",
      header: "Authority",
      render: (record) => {
        const a = authorityById.get(record.authority_id);
        return a ? (
          <span>
            {a.name} <span className="text-[var(--foreground-subtle)]">({a.slug})</span>
          </span>
        ) : (
          <span className="text-[var(--foreground-faint)]">—</span>
        );
      },
    },
    {
      key: "family",
      header: "Family",
      sortField: "document_family",
      render: (record) => (
        <span className="text-[var(--foreground-muted)]">{record.document_family ?? "—"}</span>
      ),
    },
    {
      key: "updated",
      header: "Updated",
      sortField: "updated_at",
      render: (record) => (
        <span className="text-[var(--foreground-muted)] whitespace-nowrap">
          {formatSwissDateTime(record.updated_at)}
        </span>
      ),
    },
  ];

  return (
    <ResourceContextProvider value="sources">
      <ListContextProvider value={controller}>
        <div className="px-4 py-6 sm:px-6 sm:py-8 max-w-[var(--container-max)] mx-auto space-y-4">
          <header className="space-y-1">
            <p className="text-[11px] uppercase tracking-[0.16em] font-semibold text-[var(--foreground-subtle)]">
              Source registry
            </p>
            <h1 className="font-[family:var(--font-admin-serif)] text-[28px] font-semibold text-[var(--foreground)] leading-tight">
              Sources
            </h1>
            <p className="text-[14px] text-[var(--foreground-muted)] max-w-[68ch]">
              Track source ownership, authority mapping, family, and lifecycle state in one dense
              operator list.
            </p>
          </header>

          <DataTable<SourceRecord>
            records={records}
            columns={columns}
            getRowId={(r) => String(r.id)}
            isLoading={controller.isPending}
            error={controller.error}
            sort={controller.sort}
            onSort={(field, order) => controller.setSort({ field, order })}
            onRowClick={(r) => navigate(`/sources/${encodeURIComponent(String(r.id))}/show`)}
            total={controller.total}
            page={controller.page}
            perPage={controller.perPage}
            onPageChange={controller.setPage}
            caption={
              controller.total !== undefined
                ? `${controller.total} source${controller.total === 1 ? "" : "s"}`
                : null
            }
          />
        </div>
      </ListContextProvider>
    </ResourceContextProvider>
  );
}
