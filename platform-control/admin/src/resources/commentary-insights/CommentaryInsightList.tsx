/**
 * `CommentaryInsightList` — operator surface over `/v1/commentary-insights`.
 *
 * The documented filters (`jurisdiction_id`, `authority_id`,
 * `source_document_id`, `review_state`) render as plain `<input>` /
 * `<select>` chips so the page is self-contained — we don't yet have a
 * reference picker for `source_document_id`. Each row links into the
 * edit page, and `last_correction_id` doubles as a deep-link into the
 * provenance trail.
 */
"use client";

import { ListContextProvider, ResourceContextProvider, useListController } from "ra-core";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ResourceName } from "../../domain/resourceNames";
import type {
  CommentaryInsightRecord,
  CommentaryInsightReviewState,
} from "../../lib/admin/dataProvider";
import { DataTable, type DataTableColumn, Pill } from "../../ui/primitives";
import { REVIEW_STATE_LABEL, REVIEW_STATE_VALUES, reviewStateToLevel } from "./commentaryInsight";

type CommentaryInsightFilters = {
  jurisdiction_id?: string;
  authority_id?: string;
  source_document_id?: string;
  review_state?: CommentaryInsightReviewState;
};

function FilterTextInput({
  label,
  value,
  onCommit,
  placeholder,
}: {
  label: string;
  value: string | undefined;
  onCommit: (next: string | undefined) => void;
  placeholder: string;
}) {
  // Local draft state so committing only happens on blur / Enter — avoids
  // refetching on every keystroke.
  const [draft, setDraft] = useState(value ?? "");
  return (
    <label className="flex flex-col gap-1 min-w-[200px]">
      <span className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[rgba(29,41,61,0.7)]">
        {label}
      </span>
      <input
        type="text"
        value={draft}
        placeholder={placeholder}
        onChange={(event) => setDraft(event.target.value)}
        onBlur={() => onCommit(draft.trim() === "" ? undefined : draft.trim())}
        onKeyDown={(event) => {
          if (event.key === "Enter") {
            event.currentTarget.blur();
          }
        }}
        className="rounded-xl border border-[rgba(29,41,61,0.16)] bg-white/85 px-3 py-2 text-sm text-[var(--foreground)] placeholder:text-[rgba(29,41,61,0.35)] hover:border-[rgba(29,41,61,0.28)] focus:outline-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--brand-focus-ring)]"
      />
    </label>
  );
}

function ReviewStateFilter({
  value,
  onChange,
}: {
  value: CommentaryInsightReviewState | undefined;
  onChange: (next: CommentaryInsightReviewState | undefined) => void;
}) {
  return (
    <label className="flex flex-col gap-1 min-w-[200px]">
      <span className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[rgba(29,41,61,0.7)]">
        Review state
      </span>
      <select
        value={value ?? ""}
        onChange={(event) => {
          const next = event.target.value;
          onChange(next === "" ? undefined : (next as CommentaryInsightReviewState));
        }}
        className="rounded-xl border border-[rgba(29,41,61,0.16)] bg-white/85 px-3 py-2 text-sm text-[var(--foreground)] hover:border-[rgba(29,41,61,0.28)] focus:outline-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--brand-focus-ring)]"
      >
        <option value="">Any review state</option>
        {REVIEW_STATE_VALUES.map((state) => (
          <option key={state} value={state}>
            {REVIEW_STATE_LABEL[state]}
          </option>
        ))}
      </select>
    </label>
  );
}

export default function CommentaryInsightList() {
  const controller = useListController<CommentaryInsightRecord>({
    resource: ResourceName.CommentaryInsights,
    perPage: 50,
    sort: { field: "insight_id", order: "ASC" },
  });
  const navigate = useNavigate();

  const filterValues = controller.filterValues as CommentaryInsightFilters;
  const setFilter = <K extends keyof CommentaryInsightFilters>(
    key: K,
    value: CommentaryInsightFilters[K] | undefined,
  ) => {
    const next = { ...filterValues } as Record<string, unknown>;
    if (value === undefined) {
      delete next[key as string];
    } else {
      next[key as string] = value;
    }
    controller.setFilters(next, controller.displayedFilters);
  };

  const columns: DataTableColumn<CommentaryInsightRecord>[] = [
    {
      key: "insight",
      header: "Insight",
      render: (record) => (
        <div className="flex flex-col gap-0.5">
          <span className="font-semibold text-[var(--foreground)] line-clamp-2">
            {record.claim}
          </span>
          <span className="font-mono text-[11px] text-[rgba(29,41,61,0.55)]">
            {record.insight_id}
          </span>
        </div>
      ),
    },
    {
      key: "type",
      header: "Type",
      render: (record) => <Pill variant="meta">{record.insight_type}</Pill>,
    },
    {
      key: "review",
      header: "Review state",
      render: (record) => (
        <Pill level={reviewStateToLevel(record.review_state)}>
          {REVIEW_STATE_LABEL[record.review_state] ?? record.review_state}
        </Pill>
      ),
    },
    {
      key: "jurisdiction",
      header: "Jurisdiction",
      render: (record) => (
        <span className="font-mono text-[12px] text-[rgba(29,41,61,0.8)]">
          {record.jurisdiction_id ?? "—"}
        </span>
      ),
    },
    {
      key: "confidence",
      header: "Confidence",
      render: (record) => (
        <span className="text-sm tabular-nums text-[rgba(29,41,61,0.85)]">
          {record.confidence.toFixed(2)}
        </span>
      ),
    },
    {
      key: "provenance",
      header: "Last correction",
      render: (record) =>
        record.last_correction_id ? (
          <button
            type="button"
            onClick={(event) => {
              event.stopPropagation();
              navigate(`/${ResourceName.Corrections}`);
            }}
            className="font-mono text-[12px] text-[var(--brand)] hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--brand-focus-ring)]"
          >
            {record.last_correction_id}
          </button>
        ) : (
          <span className="text-[rgba(29,41,61,0.4)]">—</span>
        ),
    },
  ];

  return (
    <ResourceContextProvider value={ResourceName.CommentaryInsights}>
      <ListContextProvider value={controller}>
        <div className="space-y-4">
          <header className="space-y-1">
            <p className="text-[11px] uppercase tracking-[0.16em] font-semibold text-[rgba(29,41,61,0.6)]">
              Commentary insights · Sprint 2
            </p>
            <h1 className="font-serif text-[28px] font-semibold text-[var(--foreground)] leading-tight">
              Commentary insights
            </h1>
            <p className="text-[14px] text-[rgba(29,41,61,0.7)] max-w-[68ch]">
              Read-side overlay over document-intelligence output. Click a row to apply an operator
              field edit; submitting writes a `field_edit` correction and updates the overlay.
            </p>
          </header>

          <div className="flex flex-wrap gap-3 rounded-[18px] border border-[rgba(29,41,61,0.08)] bg-white/85 p-4 shadow-[var(--shadow-card)] backdrop-blur-[12px]">
            <FilterTextInput
              label="Jurisdiction id"
              value={filterValues.jurisdiction_id}
              onCommit={(next) => setFilter("jurisdiction_id", next)}
              placeholder="jur_ch_federal"
            />
            <FilterTextInput
              label="Authority id"
              value={filterValues.authority_id}
              onCommit={(next) => setFilter("authority_id", next)}
              placeholder="auth_fedlex"
            />
            <FilterTextInput
              label="Source document id"
              value={filterValues.source_document_id}
              onCommit={(next) => setFilter("source_document_id", next)}
              placeholder="doc_…"
            />
            <ReviewStateFilter
              value={filterValues.review_state}
              onChange={(next) => setFilter("review_state", next)}
            />
          </div>

          <DataTable<CommentaryInsightRecord>
            records={controller.data}
            columns={columns}
            getRowId={(r) => String(r.id)}
            isLoading={controller.isPending}
            error={controller.error}
            sort={controller.sort}
            onSort={(field, order) => controller.setSort({ field, order })}
            onRowClick={(record) =>
              navigate(
                `/${ResourceName.CommentaryInsights}/${encodeURIComponent(String(record.id))}`,
              )
            }
            total={controller.total}
            page={controller.page}
            perPage={controller.perPage}
            onPageChange={controller.setPage}
            empty={
              <div className="space-y-1">
                <p className="font-semibold text-[var(--foreground)]">
                  No commentary insights match the current filters.
                </p>
                <p className="text-[12px] text-[rgba(29,41,61,0.6)]">
                  Insights flow in from document-intelligence runs — try clearing the review-state
                  filter.
                </p>
              </div>
            }
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
