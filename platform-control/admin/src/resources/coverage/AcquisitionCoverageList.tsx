/**
 * `AcquisitionCoverageList` — what we were asked to acquire, and whether it succeeded.
 *
 * The platform-control half of the ADR-0042 §4 split. legal-search answers *what does the
 * corpus hold?*; this answers *what should it hold, and how far did we get?*
 *
 *     expected → discovered → acquired → processed      [ indexed: not measured here ]
 *
 * TWO RENDERING RULES CARRY THE HONESTY OF THIS VIEW
 * --------------------------------------------------
 * 1. **A null `expected` renders as an em dash, never as `0` and never as an empty cell.**
 *    Most of the 2110 municipal rows have no denominator, and a column of zeros would read
 *    as "these communes publish no law" rather than "nobody has told us how much there is".
 * 2. **A suppressed gap is not the same as a gap of zero.** Registry-tier and truncated
 *    rows carry null gaps by construction (the API refuses to emit them), so they show a
 *    dash with the reason rather than a number that would invite subtraction.
 */
"use client";

import { ListContextProvider, ResourceContextProvider, useListController } from "ra-core";
import { useEffect, useMemo, useState } from "react";
import { ResourceName } from "../../domain/resourceNames";
import {
  type AcquisitionCoverageRecord,
  type AcquisitionCoverageSummary,
  type CoverageWorkItem,
  type CoverageWorkQueueResponse,
  controlPlaneActions,
} from "../../lib/admin/dataProvider";
import { DataTable, type DataTableColumn, Panel, Pill, type PillLevel } from "../../ui/primitives";

const EM_DASH = "—";

/**
 * The level presets.
 *
 * The list is 2,169 rows over 44 alphabetical pages, and — per the summary
 * header this page already renders — four of them have any acquisition at all.
 * Those four were unreachable without paging, because the table had no filter
 * and no sort.
 *
 * `level` is the *only* narrowing `GET /v1/acquisition-coverage` accepts
 * (`routers/coverage.py` takes `limit`, `offset`, `level`), and it is enough:
 * 2,110 of the rows are municipal, so the two chips below reduce the table to
 * ~59 rows — which is where every row with data lives today.
 *
 * A "has acquisition" preset would be the more direct answer and is
 * deliberately NOT built client-side: the endpoint is server-paginated, so a
 * filter applied to the loaded page would report "0 with acquisition" while
 * sitting on page 1 of 44. That needs a server-side predicate, which is not
 * this lane's to add.
 */
const LEVEL_PRESETS = [
  { key: "federal", label: "Federal" },
  { key: "cantonal", label: "Cantonal" },
  { key: "municipal", label: "Municipal" },
] as const;

type LevelKey = (typeof LEVEL_PRESETS)[number]["key"];

function PresetButton({
  isActive,
  onClick,
  children,
}: {
  isActive: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`inline-flex items-center rounded-full border px-3 h-8 text-[12px] font-semibold transition-colors ${
        isActive
          ? "bg-[var(--brand-wash-8)] border-[var(--brand)]/50 text-[var(--brand)]"
          : "bg-[var(--surface-panel)]/60 border-[var(--border)] text-[var(--foreground-muted)] hover:border-[var(--border-strong)]"
      }`}
    >
      {children}
    </button>
  );
}

/** A denominator's trustworthiness decides what the row is allowed to claim. */
const TIER_PRESENTATION: Record<string, { level: PillLevel; hint: string }> = {
  published: {
    level: "healthy",
    hint: "The source publishes its own count — completeness is measurable.",
  },
  registry: {
    level: "info",
    hint: "We know the units, not their contents — breadth only, never depth.",
  },
  none: {
    level: "neutral",
    hint: "No denominator. Completeness cannot be stated for this jurisdiction.",
  },
};

/** A tier the UI does not model must not be dressed up as one it does. */
const UNKNOWN_TIER = {
  level: "neutral" as PillLevel,
  hint: "Unrecognised denominator tier — treat as unstatable.",
};

function Count({ value }: { value: number | null | undefined }) {
  if (value === null || value === undefined) {
    return (
      <span className="text-[var(--foreground-subtle)]" title="No denominator recorded">
        {EM_DASH}
      </span>
    );
  }
  return <span className="tabular-nums text-[var(--foreground)]">{value}</span>;
}

function SummaryPanel({ summary }: { summary: AcquisitionCoverageSummary | null }) {
  if (!summary) {
    return null;
  }
  const stats: { label: string; value: string; hint?: string }[] = [
    { label: "Jurisdictions", value: String(summary.jurisdictions_total) },
    {
      label: "With any acquisition",
      value: String(summary.jurisdictions_with_any_acquired),
      hint: "At least one captured document.",
    },
    {
      label: "With a published denominator",
      value: String(summary.jurisdictions_with_published_denominator),
      hint: "Completeness is measurable for these.",
    },
    {
      label: "Unattributed measurements",
      value: String(summary.reconciliations_unattributed),
      hint: "Runs covering several entities — recorded, but not attributable to one jurisdiction.",
    },
    {
      label: "Processed, unattributable",
      value: String(summary.processed_documents_unattributable),
      hint: "Lifecycle events whose run no longer exists.",
    },
  ];

  return (
    <Panel>
      <div className="flex flex-wrap gap-x-8 gap-y-4 p-4">
        {stats.map((stat) => (
          <div key={stat.label} className="min-w-[10rem]" title={stat.hint}>
            <p className="text-[11px] uppercase tracking-[0.14em] font-semibold text-[var(--foreground-subtle)]">
              {stat.label}
            </p>
            <p className="text-[22px] font-semibold tabular-nums text-[var(--foreground)]">
              {stat.value}
            </p>
          </div>
        ))}
      </div>
      {summary.unmeasured_stages && summary.unmeasured_stages.length > 0 ? (
        <p className="border-t border-[var(--border-subtle)] px-4 py-3 text-[13px] text-[var(--foreground-muted)]">
          Not measured here: <strong>{summary.unmeasured_stages.join(", ")}</strong>. Whether a
          document is searchable lives in legal-search&apos;s index, which this service has no
          dependency on — reporting it from here would be an inference, not a measurement.
        </p>
      ) : null}
      {summary.reconciliations_recorded_since ? null : (
        <p className="border-t border-[var(--border-subtle)] px-4 py-3 text-[13px] text-[var(--foreground-muted)]">
          No coverage measurement has been recorded yet, so every denominator below is unknown. That
          is the starting state, not an empty result.
        </p>
      )}
    </Panel>
  );
}

/**
 * What each queue reason means, in the operator's words.
 *
 * The codes come from the server (`CoverageWorkReason`) and are the thing to
 * branch on; these are only the rendering. `no_source` is absent on purpose —
 * the server reports those as a count rather than as rows (#928), so it cannot
 * appear here.
 */
const REASON_COPY: Record<string, { label: string; level: PillLevel; hint: string }> = {
  no_denominator: {
    label: "No denominator",
    level: "neutral",
    hint: "Nothing has told us how much this jurisdiction publishes, so coverage is unstatable. Run an enumeration.",
  },
  never_acquired: {
    label: "Never acquired",
    level: "degraded",
    hint: "A source exists and nothing has been captured through it yet.",
  },
  acquisition_gap: {
    label: "Acquisition gap",
    level: "degraded",
    hint: "The source says there is more than we have captured.",
  },
  processing_gap: {
    label: "Processing gap",
    level: "info",
    hint: "Captured, not yet turned into documents. Waiting, not re-acquiring.",
  },
  holdings_exceed_denominator: {
    label: "Holds more than published",
    level: "critical",
    hint: "Not progress: a dedup failure, or a denominator counting something else. No run fixes it.",
  },
  refusals_outstanding: {
    label: "Refusals outstanding",
    level: "critical",
    hint: "A run here was refused. A person decides what happens next.",
  },
};

/**
 * What the queue's `proposed_action` means, in the operator's words.
 *
 * The codes come from the server (`CoverageWorkAction`), which is the thing to
 * branch on; this is only the rendering. Deliberately NOT re-derived from
 * `reasons` here: that mapping lived in one client, a second client re-derived it
 * from the queue's sort order, and the two disagreed about whether a refused
 * jurisdiction was the agent's to act on (#964). One definition, server-side.
 */
const ACTION_COPY: Record<string, { label: string; hint: string }> = {
  register_source: {
    label: "Register a source",
    hint: "No source exists, so there is nothing to act through. Registering one is a repo edit and a deploy (#736).",
  },
  enumerate_denominator: {
    label: "Enumerate",
    hint: "Nothing has told us how much this jurisdiction publishes. Every other answer about it is unstatable until this exists.",
  },
  run_acceptance: {
    label: "Run acceptance",
    hint: "A denominator exists and we hold less than it. An acceptance run is the evidence primitive (ADR-0030).",
  },
  await_pipeline: {
    label: "Wait for the pipeline",
    hint: "Captured, not yet processed. Running acquisition again would add to a backlog rather than clear it.",
  },
  investigate_holdings: {
    label: "Investigate holdings",
    hint: "We hold more than the source claims to publish. A dedup failure, or a denominator counting something else. No run fixes it.",
  },
  resolve_refusal: {
    label: "Resolve the refusal",
    hint: "A run here was refused. The refusal is the answer, and a person decides what happens next.",
  },
};

const queueColumns: DataTableColumn<CoverageWorkItem & { id: string }>[] = [
  {
    key: "jurisdiction",
    header: "Jurisdiction",
    render: (item) => (
      <div>
        <span className="font-semibold text-[var(--foreground)]">{item.name}</span>
        <span className="ml-2 font-mono text-[11px] text-[var(--foreground-subtle)]">
          {item.jurisdiction_id}
        </span>
      </div>
    ),
  },
  {
    key: "level",
    header: "Level",
    render: (item) => (
      <span className="text-[13px] text-[var(--foreground-muted)]">{item.level}</span>
    ),
  },
  {
    key: "why",
    header: "Why",
    render: (item) => (
      // EVERY reason, not a chosen "primary" one. The server deliberately does
      // not rank them (no score — ADR-0042), and picking one here would be the
      // client inventing the ranking the API refused to.
      <div className="flex flex-wrap gap-1">
        {item.reasons.map((reason) => {
          const copy = REASON_COPY[reason];
          return (
            <span key={reason} title={copy?.hint ?? reason}>
              <Pill level={copy?.level ?? "neutral"}>{copy?.label ?? reason}</Pill>
            </span>
          );
        })}
      </div>
    ),
  },
  {
    key: "action",
    header: "Next",
    render: (item) => {
      const copy = ACTION_COPY[item.proposed_action];
      return (
        <span
          className="text-[13px] text-[var(--foreground)]"
          title={copy?.hint ?? item.proposed_action}
        >
          {copy?.label ?? item.proposed_action}
        </span>
      );
    },
  },
  {
    key: "actor",
    header: "Who",
    render: (item) => (
      /*
       * The autonomy boundary, rendered — not decided here. `actor` is folded
       * server-side over every reason, so a refusal anywhere makes the row a
       * person's whatever the named action is (#964, ADR-0056).
       *
       * There is deliberately no action button in this column. A refusal is an
       * outcome to display, never a retry affordance: a closed config key is how
       * an operator stops traffic at a portal when an authority complains about
       * load, and a "Retry" here would be that override performed by the
       * operator's own hand without being told what they were doing.
       */
      <Pill level={item.actor === "agent" ? "info" : "neutral"}>
        {item.actor === "agent" ? "Agent" : "You"}
      </Pill>
    ),
  },
  { key: "expected", header: "Expected", render: (item) => <Count value={item.expected} /> },
  {
    key: "acquired",
    header: "Acquired",
    render: (item) => <Count value={item.acquired_distinct_urls} />,
  },
  {
    key: "processed",
    header: "Processed",
    render: (item) => <Count value={item.processed_documents} />,
  },
  {
    key: "sources",
    header: "Sources",
    render: (item) => (
      <span className="tabular-nums text-[var(--foreground-muted)]">
        {item.source_ids?.length ?? 0}
      </span>
    ),
  },
];

export function AcquisitionCoverageList() {
  const controller = useListController<AcquisitionCoverageRecord>({
    resource: ResourceName.AcquisitionCoverage,
    perPage: 50,
    sort: { field: "jurisdiction_id", order: "ASC" },
  });
  const [summary, setSummary] = useState<AcquisitionCoverageSummary | null>(null);
  /**
   * Which question this page answers.
   *
   * `work` is the default because it is the one an operator arrives with. The
   * ledger view opened on page 1 of 44 — fifty municipal rows reading
   * `expected —, acquired 0` — while its own header said four jurisdictions had
   * any acquisition, and offered no way to reach them (#930).
   *
   * `all` keeps the full ledger, unchanged. The work queue is a VIEW of it, not
   * a replacement: looking a specific jurisdiction up is still a real question.
   */
  const [view, setView] = useState<"work" | "all">("work");
  const [queue, setQueue] = useState<CoverageWorkQueueResponse | null>(null);
  const [queueError, setQueueError] = useState<unknown>(null);

  const activeLevel =
    typeof controller.filterValues?.level === "string"
      ? (controller.filterValues.level as LevelKey)
      : undefined;
  const setLevel = (level: LevelKey | undefined) =>
    controller.setFilters(level ? { level } : {}, undefined, false);

  useEffect(() => {
    let cancelled = false;
    controlPlaneActions
      .getAcquisitionCoverageSummary()
      .then((value) => {
        if (!cancelled) {
          setSummary(value);
        }
      })
      // The table is still useful without the summary; a failed header must not blank it.
      .catch(() => undefined);
    controlPlaneActions
      .getCoverageWorkQueue(50)
      .then((value) => {
        if (!cancelled) {
          setQueue(value);
        }
      })
      // Surfaced, not swallowed: an empty work view and a failed work view are
      // different answers, and the table below says which.
      .catch((error) => {
        if (!cancelled) {
          setQueueError(error);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const queueRows = useMemo(
    () => (queue?.data ?? []).map((item) => ({ ...item, id: item.jurisdiction_id })),
    [queue],
  );
  /*
   * Read straight off the server's `actor`, never re-derived from `reasons`.
   * Re-deriving is exactly #964: the mapping lived in one client, a second client
   * rebuilt it from the queue's sort order, and they disagreed about whether a
   * refused jurisdiction was the agent's to act on.
   */
  const agentOwned = useMemo(
    () => queueRows.filter((item) => item.actor === "agent").length,
    [queueRows],
  );
  const humanOwned = queueRows.length - agentOwned;

  const columns: DataTableColumn<AcquisitionCoverageRecord>[] = useMemo(
    () => [
      {
        key: "jurisdiction",
        header: "Jurisdiction",
        render: (record) => (
          <div>
            <span className="font-semibold text-[var(--foreground)]">{record.name}</span>
            <span className="ml-2 font-mono text-[11px] text-[var(--foreground-subtle)]">
              {record.jurisdiction_id}
            </span>
          </div>
        ),
      },
      {
        key: "level",
        header: "Level",
        render: (record) => (
          <span className="text-[13px] text-[var(--foreground-muted)]">{record.level}</span>
        ),
      },
      {
        key: "expected",
        header: "Expected",
        render: (record) => <Count value={record.expected} />,
      },
      {
        key: "tier",
        header: "Denominator",
        render: (record) => {
          // An ABSENT tier is unknown, not `none` — so it renders as the em dash the
          // admin uses for every missing value (#674), never as the word. `none` is a
          // real tier meaning "no denominator exists", and it gets its own pill.
          const tier = record.denominator_tier;
          if (!tier) {
            return <span className="text-[var(--foreground-subtle)]">{EM_DASH}</span>;
          }
          const presentation = TIER_PRESENTATION[tier] ?? UNKNOWN_TIER;
          return (
            <span title={presentation.hint}>
              <Pill level={presentation.level}>{tier}</Pill>
            </span>
          );
        },
      },
      {
        key: "acquired",
        header: "Acquired",
        render: (record) => <Count value={record.acquired_distinct_urls} />,
      },
      {
        key: "processed",
        header: "Processed",
        render: (record) => <Count value={record.processed_documents} />,
      },
      {
        key: "gap",
        header: "Gap",
        render: (record) => {
          if (record.acquired_gap === null || record.acquired_gap === undefined) {
            return (
              <span
                className="text-[var(--foreground-subtle)]"
                title={
                  record.denominator_truncated
                    ? "The run was capped, so it is a sample rather than a measurement."
                    : "No comparable denominator, so a gap would be invented."
                }
              >
                {EM_DASH}
              </span>
            );
          }
          return (
            <span
              className={`tabular-nums ${
                record.acquired_gap === 0
                  ? "text-[var(--foreground)]"
                  : "font-semibold text-[var(--foreground)]"
              }`}
              title={
                record.acquired_gap < 0
                  ? "We hold more than the source publishes — a dedup failure, or a denominator counting something else."
                  : undefined
              }
            >
              {record.acquired_gap}
            </span>
          );
        },
      },
    ],
    [],
  );

  return (
    <ResourceContextProvider value={ResourceName.AcquisitionCoverage}>
      <ListContextProvider value={controller}>
        <div className="px-4 py-6 sm:px-6 sm:py-8 max-w-[var(--container-max)] mx-auto space-y-4">
          <header className="space-y-1">
            <p className="text-[11px] uppercase tracking-[0.16em] font-semibold text-[var(--foreground-subtle)]">
              Acquisition
            </p>
            <h1 className="font-[family:var(--font-admin-serif)] text-[28px] font-semibold text-[var(--foreground)] leading-tight">
              Coverage
            </h1>
            <p className="text-[14px] text-[var(--foreground-muted)] max-w-[68ch]">
              What each jurisdiction&apos;s source says exists, against what we have acquired and
              processed. A dash means no denominator — not zero.
            </p>
          </header>

          <SummaryPanel summary={summary} />

          <section className="rounded-[18px] border border-[var(--border-faint)] bg-[var(--admin-panel-bg)] p-4 space-y-2 shadow-[var(--shadow-card)] backdrop-blur-[12px]">
            <div className="flex flex-wrap items-center gap-1.5">
              <PresetButton isActive={view === "work"} onClick={() => setView("work")}>
                Needs work
                {queue?.total !== undefined ? (
                  <span className="ml-1.5 tabular-nums opacity-70">{queue.total}</span>
                ) : null}
              </PresetButton>
              <PresetButton isActive={view === "all"} onClick={() => setView("all")}>
                All jurisdictions
              </PresetButton>
            </div>
            {view === "work" ? (
              <p className="text-[12px] text-[var(--foreground-subtle)]">
                {/*
                 * Ordering is the SERVER's and is echoed from the payload rather
                 * than restated, so this line cannot drift from what the rows
                 * actually do. There is no score and no chosen primary reason:
                 * a priority number needs a denominator exactly as much as a
                 * completeness percentage does (ADR-0042).
                 */}
                Jurisdictions with a source and something to act on, ordered by{" "}
                <code className="font-mono text-[11px]">{queue?.ordering ?? "the server"}</code>.
                Every reason true of a row is shown — there is no ranking and no score.
                {queue?.jurisdictions_without_a_source ? (
                  <>
                    {" "}
                    A further{" "}
                    <strong>
                      {queue.jurisdictions_without_a_source} jurisdictions have no source at all
                    </strong>{" "}
                    and are counted rather than listed: registering one is a repo edit and a deploy,
                    which is not work this queue can hand anyone.
                  </>
                ) : null}
              </p>
            ) : null}
            {view === "work" && queueRows.length > 0 ? (
              /*
               * Who owns this page of work. The operator agent (#909) already
               * decides this per item; until now nothing rendered it, so a control
               * plane that could act was invisible in the product (ADR-0056).
               *
               * Counted over the rows ON SCREEN, and it says so. The server caps
               * the queue, so a total computed here would be a claim about a
               * population this page has not seen — the ADR-0042 mistake in
               * miniature.
               */
              <p
                data-testid="queue-actor-split"
                className="text-[12px] text-[var(--foreground-subtle)]"
              >
                Of the <strong>{queueRows.length}</strong> shown, the agent can work{" "}
                <strong>{agentOwned}</strong> on its own; <strong>{humanOwned}</strong>{" "}
                {humanOwned === 1 ? "needs" : "need"} you.
                {humanOwned > 0 ? (
                  <>
                    {" "}
                    A refusal is a decision to respect, not a run to retry — so those stay yours
                    however the queue is ordered.
                  </>
                ) : null}
              </p>
            ) : null}
            {view === "all" ? (
              <div className="flex flex-wrap items-center gap-1.5">
                <PresetButton isActive={!activeLevel} onClick={() => setLevel(undefined)}>
                  All levels
                </PresetButton>
                {LEVEL_PRESETS.map((preset) => (
                  <PresetButton
                    key={preset.key}
                    isActive={activeLevel === preset.key}
                    onClick={() => setLevel(preset.key)}
                  >
                    {preset.label}
                  </PresetButton>
                ))}
              </div>
            ) : null}
            {view === "all" ? (
              <p className="text-[12px] text-[var(--foreground-subtle)]">
                {/*
                 * Says what the operator cannot do here, rather than leaving them
                 * to discover it by clicking headers that do not sort. The
                 * endpoint takes `level` and pagination and nothing else: no
                 * ordering parameter, no "has acquisition" predicate. Ordering is
                 * the server's (alphabetical), so a client-side sort control
                 * would reorder 50 of 2,169 rows and look like it had sorted the
                 * table.
                 */}
                Filtered on the server, so the count and pager below describe the whole level — not
                this page. Rows are ordered by the API (alphabetical) and this endpoint offers no
                other ordering; most municipal rows carry no acquisition yet, which is what the
                header counts say.
              </p>
            ) : null}
          </section>

          {view === "work" ? (
            <DataTable<CoverageWorkItem & { id: string }>
              records={queueRows}
              columns={queueColumns}
              getRowId={(item) => item.id}
              isLoading={queue === null && queueError === null}
              error={queueError}
              empty="Nothing needs work: every jurisdiction with a source is measured and current."
              caption={
                queue
                  ? `${queue.total} jurisdiction${queue.total === 1 ? "" : "s"} need work`
                  : null
              }
            />
          ) : (
            <DataTable<AcquisitionCoverageRecord>
              records={controller.data}
              columns={columns}
              getRowId={(r) => String(r.id)}
              isLoading={controller.isPending}
              error={controller.error}
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
          )}
        </div>
      </ListContextProvider>
    </ResourceContextProvider>
  );
}
