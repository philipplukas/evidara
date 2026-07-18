/**
 * `CommentaryInsightList` — browse view for commentary insights (#428),
 * rendered with Tailwind + `ra-core` primitives (ADR-0026).
 *
 * Lists overlay rows from `GET /v1/commentary-insights` (PR #440). Operators
 * jump from here into the editor (`CommentaryInsightShow`) to raise a
 * `field_edit` correction against an insight's claim. The review-state filter
 * is a Tailwind preset bar driven by `useListController.setFilters` rather than
 * a MUI `SelectInput`.
 */
"use client";

import { ListContextProvider, ResourceContextProvider, useListController } from "ra-core";
import { useMemo } from "react";
import { useNavigate } from "react-router-dom";
import type { CommentaryInsightRaRecord } from "../../lib/admin/dataProvider";
import { formatSwissDateTime } from "../../lib/format/date";
import { DataTable, type DataTableColumn, Pill, type PillLevel } from "../../ui/primitives";

const REVIEW_STATE_PRESETS: Array<{ key: string; label: string; level: PillLevel }> = [
  { key: "machine_generated_unreviewed", label: "Unreviewed", level: "degraded" },
  { key: "machine_verified", label: "Machine verified", level: "info" },
  { key: "editor_approved", label: "Editor approved", level: "healthy" },
  { key: "rejected", label: "Rejected", level: "critical" },
  { key: "stale", label: "Stale", level: "neutral" },
];

const REVIEW_STATE_LEVEL: Record<string, PillLevel> = Object.fromEntries(
  REVIEW_STATE_PRESETS.map((p) => [p.key, p.level]),
);

function reviewStateLevel(state: string): PillLevel {
  return REVIEW_STATE_LEVEL[state] ?? "neutral";
}

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

export function CommentaryInsightList() {
  const controller = useListController<CommentaryInsightRaRecord>({
    resource: "commentary-insights",
    perPage: 50,
    sort: { field: "updated_at", order: "DESC" },
  });
  const navigate = useNavigate();

  const records = controller.data;
  const filterValues = controller.filterValues as { review_state?: string };

  const setReviewState = (review_state: string | undefined) =>
    controller.setFilters({ ...filterValues, review_state }, undefined, false);

  const columns: DataTableColumn<CommentaryInsightRaRecord>[] = useMemo(
    () => [
      {
        key: "insight",
        header: "Insight",
        sortField: "insight_id",
        render: (record) => (
          <div className="flex flex-col gap-0.5">
            <span className="font-mono text-[12px] text-[var(--foreground)]">
              {record.insight_id}
            </span>
            <span className="text-[12px] text-[var(--foreground-subtle)]">
              {record.document_id}
            </span>
          </div>
        ),
      },
      {
        key: "type",
        header: "Type",
        sortField: "insight_type",
        render: (record) => <Pill variant="meta">{record.insight_type}</Pill>,
      },
      {
        key: "claim",
        header: "Claim",
        render: (record) => (
          <span className="text-[var(--foreground-muted)] line-clamp-2 max-w-[52ch]">
            {record.claim ? record.claim.slice(0, 80) : "—"}
          </span>
        ),
      },
      {
        key: "review",
        header: "Review state",
        sortField: "review_state",
        render: (record) => (
          <Pill level={reviewStateLevel(record.review_state)}>{record.review_state}</Pill>
        ),
      },
      {
        key: "rev",
        header: "Rev",
        sortField: "overlay_revision",
        className: "text-right tabular-nums",
        headerClassName: "text-right",
        render: (record) => record.overlay_revision,
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
    <ResourceContextProvider value="commentary-insights">
      <ListContextProvider value={controller}>
        <div className="px-4 py-6 sm:px-6 sm:py-8 max-w-[var(--container-max)] mx-auto space-y-4">
          <header className="space-y-1">
            <p className="text-[11px] uppercase tracking-[0.16em] font-semibold text-[var(--foreground-subtle)]">
              Commentary overlay
            </p>
            <h1 className="font-[family:var(--font-admin-serif)] text-[28px] font-semibold text-[var(--foreground)] leading-tight">
              Commentary insights
            </h1>
            <p className="text-[14px] text-[var(--foreground-muted)] max-w-[72ch]">
              Browse machine-generated commentary insights and open one to raise a field-edit
              correction against its claim.
            </p>
          </header>

          {/* Preset bar (replaces the MUI SelectInput review-state filter). */}
          <section className="rounded-[18px] border border-[var(--border-faint)] bg-[var(--admin-panel-bg)] p-4 shadow-[var(--shadow-card)] backdrop-blur-[12px]">
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="text-[11px] uppercase tracking-[0.12em] font-semibold text-[var(--foreground-subtle)] w-[90px]">
                Review state
              </span>
              <PresetButton
                isActive={!filterValues.review_state}
                onClick={() => setReviewState(undefined)}
              >
                All
              </PresetButton>
              {REVIEW_STATE_PRESETS.map((preset) => (
                <PresetButton
                  key={preset.key}
                  isActive={filterValues.review_state === preset.key}
                  onClick={() => setReviewState(preset.key)}
                >
                  {preset.label}
                </PresetButton>
              ))}
            </div>
          </section>

          <DataTable<CommentaryInsightRaRecord>
            records={records}
            columns={columns}
            getRowId={(r) => String(r.id)}
            isLoading={controller.isPending}
            error={controller.error}
            sort={controller.sort}
            onSort={(field, order) => controller.setSort({ field, order })}
            onRowClick={(r) =>
              navigate(`/commentary-insights/${encodeURIComponent(String(r.id))}/show`)
            }
            getRowLabel={(r) => `Open commentary insight ${r.insight_id}`}
            total={controller.total}
            page={controller.page}
            perPage={controller.perPage}
            onPageChange={controller.setPage}
            empty="No commentary insights match the current filter."
            caption={
              controller.total !== undefined
                ? `${controller.total} insight${controller.total === 1 ? "" : "s"}`
                : null
            }
          />
        </div>
      </ListContextProvider>
    </ResourceContextProvider>
  );
}
