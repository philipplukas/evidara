/**
 * `CorrectionQueueList` — Sprint 2 correction queue surface for in-house
 * analysts. Reads `/v1/corrections/queue` with `status=pending` by
 * default; surfaces the documented filters (`target_entity_type`,
 * `correction_type`, `status`) as plain `<select>` chips.
 *
 * Built on the Tailwind + ra-core pattern (no MUI). The row click links
 * out to the commentary insight edit page when the target is a
 * `commentary_insight`; other targets remain inert until Sprint 3 widens
 * the editor surface.
 *
 * The pure label/colour/href helpers live in `./correctionQueue.ts` so
 * they stay unit-testable under the node-environment Vitest config.
 */
"use client";

import { ListContextProvider, ResourceContextProvider, useListController } from "ra-core";
import { useNavigate } from "react-router-dom";
import { ResourceName } from "../../domain/resourceNames";
import type {
  CorrectionRecord,
  CorrectionStatus,
  CorrectionTargetEntityType,
  CorrectionType,
} from "../../lib/admin/dataProvider";
import { formatSwissDateTime } from "../../lib/format/date";
import { DataTable, type DataTableColumn, Pill } from "../../ui/primitives";
import {
  buildCorrectionFollowUpHref,
  CORRECTION_STATUS_LABEL,
  CORRECTION_TARGET_LABEL,
  CORRECTION_TYPE_LABEL,
  correctionStatusToLevel,
  DEFAULT_CORRECTION_QUEUE_FILTER,
  summarizeRationale,
} from "./correctionQueue";

const TARGET_CHOICES: Array<{ value: CorrectionTargetEntityType; label: string }> = (
  Object.keys(CORRECTION_TARGET_LABEL) as CorrectionTargetEntityType[]
).map((value) => ({ value, label: CORRECTION_TARGET_LABEL[value] }));

const TYPE_CHOICES: Array<{ value: CorrectionType; label: string }> = (
  Object.keys(CORRECTION_TYPE_LABEL) as CorrectionType[]
).map((value) => ({ value, label: CORRECTION_TYPE_LABEL[value] }));

const STATUS_CHOICES: Array<{ value: CorrectionStatus; label: string }> = (
  Object.keys(CORRECTION_STATUS_LABEL) as CorrectionStatus[]
).map((value) => ({ value, label: CORRECTION_STATUS_LABEL[value] }));

function FilterSelect<T extends string>({
  label,
  value,
  onChange,
  choices,
  allLabel,
}: {
  label: string;
  value: T | undefined;
  onChange: (next: T | undefined) => void;
  choices: Array<{ value: T; label: string }>;
  allLabel: string;
}) {
  return (
    <label className="flex flex-col gap-1 min-w-[160px]">
      <span className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[rgba(29,41,61,0.7)]">
        {label}
      </span>
      <select
        value={value ?? ""}
        onChange={(event) => {
          const next = event.target.value;
          onChange(next === "" ? undefined : (next as T));
        }}
        className="rounded-xl border border-[rgba(29,41,61,0.16)] bg-white/85 px-3 py-2 text-sm text-[var(--foreground)] hover:border-[rgba(29,41,61,0.28)] focus:outline-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--brand-focus-ring)]"
      >
        <option value="">{allLabel}</option>
        {choices.map((choice) => (
          <option key={choice.value} value={choice.value}>
            {choice.label}
          </option>
        ))}
      </select>
    </label>
  );
}

export default function CorrectionQueueList() {
  const controller = useListController<CorrectionRecord>({
    resource: ResourceName.Corrections,
    perPage: 50,
    sort: { field: "created_at", order: "DESC" },
    filterDefaultValues: DEFAULT_CORRECTION_QUEUE_FILTER,
  });
  const navigate = useNavigate();

  const filterValues = controller.filterValues as {
    status?: CorrectionStatus;
    target_entity_type?: CorrectionTargetEntityType;
    correction_type?: CorrectionType;
  };

  const setFilter = <K extends keyof typeof filterValues>(
    key: K,
    value: (typeof filterValues)[K] | undefined,
  ) => {
    const next = { ...filterValues } as Record<string, unknown>;
    if (value === undefined) {
      delete next[key as string];
    } else {
      next[key as string] = value;
    }
    controller.setFilters(next, controller.displayedFilters);
  };

  const columns: DataTableColumn<CorrectionRecord>[] = [
    {
      key: "type",
      header: "Type",
      render: (record) => (
        <div className="flex flex-col gap-0.5">
          <span className="font-semibold text-[var(--foreground)]">
            {CORRECTION_TYPE_LABEL[record.correction_type] ?? record.correction_type}
          </span>
          <span className="font-mono text-[11px] text-[rgba(29,41,61,0.55)]">
            {record.correction_id}
          </span>
        </div>
      ),
    },
    {
      key: "target",
      header: "Target",
      render: (record) => (
        <div className="flex flex-col gap-0.5">
          <span className="text-sm text-[var(--foreground)]">
            {CORRECTION_TARGET_LABEL[record.target_entity_type] ?? record.target_entity_type}
          </span>
          <span className="font-mono text-[11px] text-[rgba(29,41,61,0.55)]">
            {record.target_entity_id}
          </span>
        </div>
      ),
    },
    {
      key: "status",
      header: "Status",
      render: (record) => (
        <Pill level={correctionStatusToLevel(record.status)}>
          {CORRECTION_STATUS_LABEL[record.status] ?? record.status}
        </Pill>
      ),
    },
    {
      key: "operator",
      header: "Operator",
      render: (record) => (
        <span className="font-mono text-[12px] text-[rgba(29,41,61,0.8)]">
          {record.operator_id}
        </span>
      ),
    },
    {
      key: "rationale",
      header: "Rationale",
      render: (record) => (
        <span className="text-sm text-[rgba(29,41,61,0.85)]">
          {summarizeRationale(record.rationale)}
        </span>
      ),
    },
    {
      key: "created",
      header: "Created",
      sortField: "created_at",
      render: (record) => (
        <span className="whitespace-nowrap text-[rgba(29,41,61,0.75)]">
          {formatSwissDateTime(record.created_at)}
        </span>
      ),
    },
  ];

  return (
    <ResourceContextProvider value={ResourceName.Corrections}>
      <ListContextProvider value={controller}>
        <div className="space-y-4">
          <header className="space-y-1">
            <p className="text-[11px] uppercase tracking-[0.16em] font-semibold text-[rgba(29,41,61,0.6)]">
              Correction queue · Sprint 2
            </p>
            <h1 className="font-serif text-[28px] font-semibold text-[var(--foreground)] leading-tight">
              Pending corrections
            </h1>
            <p className="text-[14px] text-[rgba(29,41,61,0.7)] max-w-[68ch]">
              Operator worklist for the correction envelope. Click a row to drill into the target
              entity. New entries land here whenever an in-house analyst submits a field edit on a
              commentary insight.
            </p>
          </header>

          <div className="flex flex-wrap gap-3 rounded-[18px] border border-[rgba(29,41,61,0.08)] bg-white/85 p-4 shadow-[var(--shadow-card)] backdrop-blur-[12px]">
            <FilterSelect<CorrectionStatus>
              label="Status"
              value={filterValues.status}
              onChange={(next) => setFilter("status", next)}
              choices={STATUS_CHOICES}
              allLabel="Any status"
            />
            <FilterSelect<CorrectionTargetEntityType>
              label="Target type"
              value={filterValues.target_entity_type}
              onChange={(next) => setFilter("target_entity_type", next)}
              choices={TARGET_CHOICES}
              allLabel="Any target"
            />
            <FilterSelect<CorrectionType>
              label="Correction type"
              value={filterValues.correction_type}
              onChange={(next) => setFilter("correction_type", next)}
              choices={TYPE_CHOICES}
              allLabel="Any type"
            />
          </div>

          <DataTable<CorrectionRecord>
            records={controller.data}
            columns={columns}
            getRowId={(r) => String(r.id)}
            isLoading={controller.isPending}
            error={controller.error}
            sort={controller.sort}
            onSort={(field, order) => controller.setSort({ field, order })}
            onRowClick={(record) => {
              const href = buildCorrectionFollowUpHref(record);
              if (href) navigate(href);
            }}
            total={controller.total}
            page={controller.page}
            perPage={controller.perPage}
            onPageChange={controller.setPage}
            empty={
              <div className="space-y-1">
                <p className="font-semibold text-[var(--foreground)]">
                  No corrections match the current filters.
                </p>
                <p className="text-[12px] text-[rgba(29,41,61,0.6)]">
                  Try clearing the status filter to see applied or rejected entries.
                </p>
              </div>
            }
            caption={
              controller.total !== undefined
                ? `${controller.total} correction${controller.total === 1 ? "" : "s"} · ${
                    filterValues.status
                      ? CORRECTION_STATUS_LABEL[filterValues.status]
                      : "all statuses"
                  }`
                : null
            }
          />

          {/* Per-row description for screen-reader users (matches DataTable's
              row-click semantics). Inline so the queue page is self-contained. */}
          <p className="sr-only">
            Click a row to open the linked commentary insight. Rows for other entity types are
            currently view-only — drill-in surfaces ship in a follow-up sprint.
          </p>
        </div>
      </ListContextProvider>
    </ResourceContextProvider>
  );
}
