"use client";

import { useEffect, useMemo, useState } from "react";
import { useRedirect } from "react-admin";
import { ResourceName } from "../../domain/resourceNames";
import { formatSwissDateTime } from "../../lib/format/date";
import { DataTable, type DataTableColumn, InlineAlert, Panel, Spinner } from "../../ui/primitives";

type SourceItem = {
  source_id: string;
  name: string;
  status: string;
};

type RunItem = {
  run_id: string;
  source_id: string;
  status: string;
  mode: string;
  created_at: string;
  completed_at: string | null;
};

type SourceVersionItem = {
  source_version_id: string;
  source_id: string;
  version_label: string;
  status: string;
};

/**
 * The outcome of asking one source for its versions.
 *
 * A plain `SourceVersionItem[]` cannot express the difference between "this
 * source has no versions" and "we could not find out", and this card used to
 * collapse the second into the first: the fetch did `if (!res.ok) return []`,
 * so a 500 from `/v1/sources/{id}/versions` arrived at the table as an empty
 * list and rendered as the same dash two genuinely version-less rows carry
 * (#953). Unknown is not zero (ADR-0052) — so the unknown gets its own shape,
 * and the renderer has to handle it.
 */
export type SourceVersionsFetch =
  | { source_id: string; ok: true; versions: SourceVersionItem[] }
  | { source_id: string; ok: false; reason: string };

type SourceHealthRow = {
  source_id: string;
  name: string;
  totalRuns: number;
  failedRuns: number;
  successRate: number | null;
  lastRunDate: string | null;
  versionLabel: string | null;
  versionStatus: string | null;
  /**
   * Why this row's version could not be read, or `null` when it was read fine.
   * Non-null and `versionLabel === null` together mean "unknown"; both null
   * mean "this source genuinely has no versions".
   */
  versionUnavailableReason: string | null;
};

type StatusDotLevel = "healthy" | "degraded" | "critical" | "neutral";

const API_PREFIX = "/api/platform-control";

/** The em dash the coverage ledger already uses for "no value", never for "failed". */
const EM_DASH = "—";
function deriveStatusLevel(successRate: number | null): StatusDotLevel {
  if (successRate === null) return "neutral";
  if (successRate > 80) return "healthy";
  if (successRate >= 50) return "degraded";
  return "critical";
}

const STATUS_DOT_CLASS: Record<StatusDotLevel, string> = {
  healthy: "bg-[var(--status-healthy)]",
  degraded: "bg-[var(--status-degraded)]",
  critical: "bg-[var(--status-critical)]",
  neutral: "bg-[var(--status-neutral)]",
};

const STATUS_DOT_LABELS: Record<StatusDotLevel, string> = {
  healthy: "OK",
  degraded: "Warn",
  critical: "Failing",
  neutral: "No data",
};

function formatRelativeTime(isoDate: string | null): string {
  if (!isoDate) return "-";
  const now = Date.now();
  const then = new Date(isoDate).getTime();
  if (Number.isNaN(then)) return "-";

  const diffMs = now - then;
  if (diffMs < 0) return "just now";

  const minutes = Math.floor(diffMs / 60_000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;

  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;

  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}d ago`;

  return formatSwissDateTime(isoDate);
}

function formatSuccessRate(total: number, failed: number, rate: number | null): string {
  if (rate === null) return "-";
  const succeeded = total - failed;
  return `${Math.round(rate)}% (${succeeded}/${total})`;
}

/**
 * The VERSION cell, as text.
 *
 * Three outcomes, three strings — and the third is the one #953 was about. A
 * row whose version list could not be read must not read as a row that has no
 * versions: that is a failure presented as a finding.
 */
export function formatVersionInfo(row: {
  versionLabel: string | null;
  versionStatus: string | null;
  versionUnavailableReason: string | null;
}): string {
  if (row.versionUnavailableReason !== null) return `${EM_DASH} unavailable`;
  if (!row.versionLabel) return EM_DASH;
  return row.versionStatus ? `${row.versionLabel} (${row.versionStatus})` : row.versionLabel;
}

/**
 * Ask one source for its versions, keeping a failure as a failure.
 *
 * Exported because this is where the defect lived: the `catch` and the
 * `!res.ok` branch both used to `return []`, which is the API's own way of
 * saying "none", and nothing downstream could tell the two apart.
 */
export async function fetchSourceVersions(source_id: string): Promise<SourceVersionsFetch> {
  try {
    const res = await fetch(`${API_PREFIX}/v1/sources/${source_id}/versions`);
    if (!res.ok) {
      return { source_id, ok: false, reason: `HTTP ${res.status}` };
    }
    const body = (await res.json()) as { data?: SourceVersionItem[] };
    if (!Array.isArray(body.data)) {
      // A 200 whose body is not the documented shape is not an empty list
      // either — it is a response we did not understand.
      return { source_id, ok: false, reason: "unrecognised response body" };
    }
    return { source_id, ok: true, versions: body.data };
  } catch (err) {
    return {
      source_id,
      ok: false,
      reason: err instanceof Error ? err.message : "request failed",
    };
  }
}

export function computeSourceHealth(
  sources: SourceItem[],
  runs: RunItem[],
  versionFetches: SourceVersionsFetch[],
): SourceHealthRow[] {
  const runsBySource = new Map<string, RunItem[]>();
  for (const run of runs) {
    const existing = runsBySource.get(run.source_id);
    if (existing) {
      existing.push(run);
    } else {
      runsBySource.set(run.source_id, [run]);
    }
  }

  const latestVersionBySource = new Map<string, SourceVersionItem>();
  const unavailableReasonBySource = new Map<string, string>();
  for (const fetched of versionFetches) {
    if (!fetched.ok) {
      unavailableReasonBySource.set(fetched.source_id, fetched.reason);
      continue;
    }
    for (const version of fetched.versions) {
      if (!latestVersionBySource.has(version.source_id)) {
        latestVersionBySource.set(version.source_id, version);
      }
    }
  }

  return sources.map((source) => {
    const sourceRuns = runsBySource.get(source.source_id) ?? [];
    const totalRuns = sourceRuns.length;
    const failedRuns = sourceRuns.filter((r) => r.status === "failed").length;
    const completedOrFailed = sourceRuns.filter(
      (r) => r.status === "completed" || r.status === "failed",
    ).length;
    const successRate =
      completedOrFailed > 0 ? ((completedOrFailed - failedRuns) / completedOrFailed) * 100 : null;

    const sortedRuns = [...sourceRuns].sort(
      (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
    );
    const lastRunDate = sortedRuns[0]?.created_at ?? null;

    const version = latestVersionBySource.get(source.source_id);
    const unavailableReason = unavailableReasonBySource.get(source.source_id) ?? null;

    return {
      source_id: source.source_id,
      name: source.name,
      totalRuns,
      failedRuns,
      successRate,
      lastRunDate,
      // A failed read reports no label, so the two cannot be set at once and
      // `formatVersionInfo` never has to rank them.
      versionLabel: unavailableReason === null ? (version?.version_label ?? null) : null,
      versionStatus: unavailableReason === null ? (version?.status ?? null) : null,
      versionUnavailableReason: unavailableReason,
    };
  });
}

export function SourceHealthCard() {
  const [sources, setSources] = useState<SourceItem[] | null>(null);
  const [runs, setRuns] = useState<RunItem[] | null>(null);
  const [versions, setVersions] = useState<SourceVersionsFetch[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const redirect = useRedirect();

  useEffect(() => {
    let cancelled = false;

    async function fetchData() {
      try {
        const [sourcesRes, runsRes] = await Promise.all([
          fetch(`${API_PREFIX}/v1/sources`).then((res) => {
            if (!res.ok) throw new Error(`Sources fetch failed: ${res.status}`);
            return res.json() as Promise<{ data: SourceItem[] }>;
          }),
          fetch(`${API_PREFIX}/v1/runs`).then((res) => {
            if (!res.ok) throw new Error(`Runs fetch failed: ${res.status}`);
            return res.json() as Promise<{ data: RunItem[] }>;
          }),
        ]);

        if (cancelled) return;

        const allSources = sourcesRes.data;
        const sevenDaysAgo = new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString();
        const recentRuns = runsRes.data.filter((run) => run.created_at >= sevenDaysAgo);

        // One request per source. A failure here is per-row, not fatal — the
        // other columns are still true — so it is carried into the row rather
        // than thrown, and rendered as "unavailable" rather than as "none".
        const versionResults = await Promise.all(
          allSources.map((source) => fetchSourceVersions(source.source_id)),
        );

        if (cancelled) return;

        setSources(allSources);
        setRuns(recentRuns);
        setVersions(versionResults);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Unable to load source health data.");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void fetchData();
    return () => {
      cancelled = true;
    };
  }, []);

  const healthRows = useMemo(() => {
    if (!sources || !runs || !versions) return [];
    return computeSourceHealth(sources, runs, versions);
  }, [sources, runs, versions]);

  if (loading) {
    return (
      <Panel className="p-5">
        <SourceHealthHeader description="Loading source health scorecard..." />
        <div className="mt-4">
          <Spinner label="Fetching sources and recent runs..." />
        </div>
      </Panel>
    );
  }

  if (error) {
    return (
      <Panel className="p-5">
        <SourceHealthHeader />
        <InlineAlert tone="warning" className="mt-4">
          {error}
        </InlineAlert>
      </Panel>
    );
  }

  const columns: DataTableColumn<SourceHealthRow>[] = [
    {
      key: "name",
      header: "Source name",
      render: (row) => <span className="font-semibold">{row.name}</span>,
    },
    {
      key: "status",
      header: "Status",
      render: (row) => {
        const level = deriveStatusLevel(row.successRate);
        return (
          <span className="inline-flex items-center gap-2">
            <span
              className={`h-2.5 w-2.5 shrink-0 rounded-full ${STATUS_DOT_CLASS[level]}`}
              aria-hidden
            />
            <span>{STATUS_DOT_LABELS[level]}</span>
          </span>
        );
      },
    },
    {
      key: "successRate",
      header: "Success rate",
      render: (row) => formatSuccessRate(row.totalRuns, row.failedRuns, row.successRate),
    },
    {
      key: "lastRun",
      header: "Last run",
      render: (row) => formatRelativeTime(row.lastRunDate),
    },
    {
      key: "version",
      header: "Version",
      render: (row) =>
        row.versionUnavailableReason !== null ? (
          <span
            className="text-[var(--status-degraded)]"
            title={`The version list for this source could not be read (${row.versionUnavailableReason}). This is not evidence that it has no versions.`}
            data-testid="source-health-version-unavailable"
          >
            {formatVersionInfo(row)}
          </span>
        ) : (
          formatVersionInfo(row)
        ),
    },
  ];

  const unavailableCount = healthRows.filter((row) => row.versionUnavailableReason !== null).length;

  return (
    <Panel className="p-5">
      <SourceHealthHeader description="Per-source success rates from runs in the last 7 days. Click a row to inspect the source." />
      {unavailableCount > 0 ? (
        <InlineAlert tone="warning" className="mt-4" testId="source-health-versions-degraded">
          {`${unavailableCount} of ${healthRows.length} sources did not return a version list. Those rows read “${EM_DASH} unavailable”, which is not the same as having no version — the dash alone means none.`}
        </InlineAlert>
      ) : null}
      <div className="mt-4">
        <DataTable
          records={healthRows}
          columns={columns}
          getRowId={(row) => row.source_id}
          onRowClick={(row) => redirect("show", ResourceName.Sources, row.source_id)}
          getRowLabel={(row) => `Open source ${row.name}`}
          empty="No sources found. Create a source to see health data here."
        />
      </div>
    </Panel>
  );
}

function SourceHealthHeader({ description }: { description?: string }) {
  return (
    <div>
      <h2 className="text-xl font-bold leading-tight text-[var(--foreground)]">Source health</h2>
      {description ? <p className="mt-1 text-sm text-[var(--text-muted)]">{description}</p> : null}
    </div>
  );
}
