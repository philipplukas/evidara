/**
 * `CorrectionsList` — operator queue for HITL corrections (#428), rendered with
 * Tailwind + `ra-core` primitives (ADR-0026: replaced the MUI `<List>`/`<Datagrid>`
 * scaffolding once the Tailwind primitives reached parity — see #501/#516 for the
 * sources/reference-data precedents).
 *
 * Lists corrections newest-first; the default filter pins the queue to
 * `status=pending` so operators see what needs action first. Status /
 * correction-type / target-type filters are Tailwind preset buttons driven by
 * `useListController.setFilters` (the RunList pattern) rather than MUI
 * `SelectInput`. The dataProvider talks to `GET /v1/corrections` (PR #440);
 * column shape mirrors the contract envelope frozen in PR #434.
 */
"use client";

import { ListContextProvider, ResourceContextProvider, useListController } from "ra-core";
import { useMemo } from "react";
import { useNavigate } from "react-router-dom";
import type { CorrectionRecord } from "../../lib/admin/dataProvider";
import { formatSwissDateTime } from "../../lib/format/date";
import { Button, DataTable, type DataTableColumn, Pill, type PillLevel } from "../../ui/primitives";

type CorrectionStatus = CorrectionRecord["status"];
type CorrectionFilterValues = Partial<
  Pick<CorrectionRecord, "status" | "correction_type" | "target_entity_type">
>;

const STATUS_PRESETS: Array<{ key: CorrectionStatus; label: string; level: PillLevel }> = [
  { key: "pending", label: "Pending", level: "degraded" },
  { key: "applied", label: "Applied", level: "healthy" },
  { key: "rejected", label: "Rejected", level: "critical" },
  { key: "superseded", label: "Superseded", level: "neutral" },
];

const STATUS_LEVEL: Record<CorrectionStatus, PillLevel> = {
  pending: "degraded",
  applied: "healthy",
  rejected: "critical",
  superseded: "neutral",
};

const TYPE_PRESETS: Array<{ key: CorrectionRecord["correction_type"]; label: string }> = [
  { key: "field_edit", label: "Field edit" },
  { key: "annotation", label: "Annotation" },
  { key: "reject", label: "Reject" },
  { key: "rescore_request", label: "Rescore request" },
];

const TARGET_PRESETS: Array<{ key: CorrectionRecord["target_entity_type"]; label: string }> = [
  { key: "source", label: "Source" },
  { key: "document", label: "Document" },
  { key: "commentary_insight", label: "Commentary insight" },
];

/**
 * The active filters, named the way the preset bar names them.
 *
 * The queue defaults to `status=pending`, so its empty state read "No
 * corrections match the current filter." — which an operator cannot tell apart
 * from "no corrections exist" (#674). Naming the filters that are actually
 * applied makes the distinction readable, and an empty result gets the
 * "Show all corrections" escape hatch that an unfiltered empty result does not
 * need.
 *
 * Pure on purpose: the labels are the assertable part, so they are unit-tested
 * without rendering the list.
 */
export const describeActiveCorrectionFilters = (filters: CorrectionFilterValues): string[] => {
  const labelOf = <T extends string>(presets: Array<{ key: T; label: string }>, key: T) =>
    presets.find((preset) => preset.key === key)?.label ?? key;

  const active: string[] = [];
  if (filters.status) active.push(`status: ${labelOf(STATUS_PRESETS, filters.status)}`);
  if (filters.correction_type) {
    active.push(`type: ${labelOf(TYPE_PRESETS, filters.correction_type)}`);
  }
  if (filters.target_entity_type) {
    active.push(`target: ${labelOf(TARGET_PRESETS, filters.target_entity_type)}`);
  }
  return active;
};

interface PresetButtonProps {
  isActive: boolean;
  onClick: () => void;
  children: React.ReactNode;
}

function PresetButton({ isActive, onClick, children }: PresetButtonProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`inline-flex items-center rounded-full border px-3 h-8 text-[12px] font-semibold transition-colors ${
        isActive
          ? "bg-[var(--brand-wash-8)] border-[var(--brand)]/50 text-[var(--brand)]"
          : "bg-white/60 border-[var(--border)] text-[var(--foreground-muted)] hover:border-[var(--border-strong)]"
      }`}
    >
      {children}
    </button>
  );
}

export function CorrectionsList() {
  const controller = useListController<CorrectionRecord>({
    resource: "corrections",
    perPage: 50,
    sort: { field: "created_at", order: "DESC" },
    filterDefaultValues: { status: "pending" },
  });
  const navigate = useNavigate();

  const records = controller.data;
  const filterValues = controller.filterValues as CorrectionFilterValues;

  const setFilter = (patch: CorrectionFilterValues) =>
    controller.setFilters({ ...filterValues, ...patch }, undefined, false);

  const activeFilters = describeActiveCorrectionFilters(filterValues);
  const emptyState =
    activeFilters.length > 0 ? (
      <div className="flex flex-col items-center gap-2">
        <span>{`No corrections match ${activeFilters.join(" · ")}.`}</span>
        <Button
          size="sm"
          variant="secondary"
          onClick={() => controller.setFilters({}, undefined, false)}
        >
          Show all corrections
        </Button>
      </div>
    ) : (
      "No corrections exist yet."
    );

  const columns: DataTableColumn<CorrectionRecord>[] = useMemo(
    () => [
      {
        key: "correction",
        header: "Correction",
        sortField: "correction_id",
        render: (record) => (
          <div className="flex flex-col gap-1">
            <span className="font-mono text-[12px] text-[var(--foreground)]">
              {record.correction_id}
            </span>
            <Pill level={STATUS_LEVEL[record.status]}>{record.status}</Pill>
          </div>
        ),
      },
      {
        key: "type",
        header: "Type",
        sortField: "correction_type",
        render: (record) => <Pill variant="meta">{record.correction_type}</Pill>,
      },
      {
        key: "target",
        header: "Target",
        render: (record) => (
          <div className="flex flex-col gap-0.5">
            <span className="text-[var(--foreground-muted)]">{record.target_entity_type}</span>
            <span className="font-mono text-[12px] text-[var(--foreground-subtle)]">
              {record.target_entity_id}
            </span>
          </div>
        ),
      },
      {
        key: "rationale",
        header: "Rationale",
        render: (record) => (
          <span className="text-[var(--foreground-muted)] line-clamp-2 max-w-[42ch]">
            {record.rationale ?? <span className="text-[var(--foreground-faint)]">—</span>}
          </span>
        ),
      },
      {
        key: "created",
        header: "Created",
        sortField: "created_at",
        render: (record) => (
          <span className="text-[var(--foreground-muted)] whitespace-nowrap">
            {formatSwissDateTime(record.created_at) || "—"}
          </span>
        ),
      },
    ],
    [],
  );

  return (
    <ResourceContextProvider value="corrections">
      <ListContextProvider value={controller}>
        <div className="px-4 py-6 sm:px-6 sm:py-8 max-w-[var(--container-max)] mx-auto space-y-4">
          <header className="space-y-1">
            <p className="text-[11px] uppercase tracking-[0.16em] font-semibold text-[var(--foreground-subtle)]">
              Human-in-the-loop
            </p>
            <h1 className="font-[family:var(--font-admin-serif)] text-[28px] font-semibold text-[var(--foreground)] leading-tight">
              Corrections queue
            </h1>
            <p className="text-[14px] text-[var(--foreground-muted)] max-w-[72ch]">
              Triage operator corrections against sources, documents, and commentary insights. The
              queue defaults to pending items — the transitions that still need an action.
            </p>
          </header>

          {/* Preset bar (replaces the MUI SelectInput filters). */}
          <section className="rounded-[18px] border border-[var(--border-faint)] bg-[var(--admin-panel-bg)] p-4 space-y-3 shadow-[var(--shadow-card)] backdrop-blur-[12px]">
            <div className="flex flex-col gap-2">
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="text-[11px] uppercase tracking-[0.12em] font-semibold text-[var(--foreground-subtle)] w-[70px]">
                  Status
                </span>
                <PresetButton
                  isActive={!filterValues.status}
                  onClick={() => setFilter({ status: undefined })}
                >
                  All
                </PresetButton>
                {STATUS_PRESETS.map((preset) => (
                  <PresetButton
                    key={preset.key}
                    isActive={filterValues.status === preset.key}
                    onClick={() => setFilter({ status: preset.key })}
                  >
                    {preset.label}
                  </PresetButton>
                ))}
              </div>
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="text-[11px] uppercase tracking-[0.12em] font-semibold text-[var(--foreground-subtle)] w-[70px]">
                  Type
                </span>
                <PresetButton
                  isActive={!filterValues.correction_type}
                  onClick={() => setFilter({ correction_type: undefined })}
                >
                  All
                </PresetButton>
                {TYPE_PRESETS.map((preset) => (
                  <PresetButton
                    key={preset.key}
                    isActive={filterValues.correction_type === preset.key}
                    onClick={() => setFilter({ correction_type: preset.key })}
                  >
                    {preset.label}
                  </PresetButton>
                ))}
              </div>
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="text-[11px] uppercase tracking-[0.12em] font-semibold text-[var(--foreground-subtle)] w-[70px]">
                  Target
                </span>
                <PresetButton
                  isActive={!filterValues.target_entity_type}
                  onClick={() => setFilter({ target_entity_type: undefined })}
                >
                  All
                </PresetButton>
                {TARGET_PRESETS.map((preset) => (
                  <PresetButton
                    key={preset.key}
                    isActive={filterValues.target_entity_type === preset.key}
                    onClick={() => setFilter({ target_entity_type: preset.key })}
                  >
                    {preset.label}
                  </PresetButton>
                ))}
              </div>
            </div>
          </section>

          <DataTable<CorrectionRecord>
            records={records}
            columns={columns}
            getRowId={(r) => String(r.id)}
            isLoading={controller.isPending}
            error={controller.error}
            sort={controller.sort}
            onSort={(field, order) => controller.setSort({ field, order })}
            onRowClick={(r) => navigate(`/corrections/${encodeURIComponent(String(r.id))}/show`)}
            getRowLabel={(r) => `Open correction ${r.correction_id}`}
            total={controller.total}
            page={controller.page}
            perPage={controller.perPage}
            onPageChange={controller.setPage}
            empty={emptyState}
            caption={
              controller.total !== undefined
                ? `${controller.total} correction${controller.total === 1 ? "" : "s"}`
                : null
            }
          />
        </div>
      </ListContextProvider>
    </ResourceContextProvider>
  );
}
