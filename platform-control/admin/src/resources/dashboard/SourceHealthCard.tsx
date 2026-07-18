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

type SourceHealthRow = {
  source_id: string;
  name: string;
  totalRuns: number;
  failedRuns: number;
  successRate: number | null;
  lastRunDate: string | null;
  versionLabel: string | null;
  versionStatus: string | null;
};

type StatusDotLevel = "healthy" | "degraded" | "critical" | "neutral";

const API_PREFIX = "/api/platform-control";
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

function formatVersionInfo(label: string | null, status: string | null): string {
  if (!label) return "-";
  return status ? `${label} (${status})` : label;
}

function computeSourceHealth(
  sources: SourceItem[],
  runs: RunItem[],
  versions: SourceVersionItem[],
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
  for (const version of versions) {
    const existing = latestVersionBySource.get(version.source_id);
    if (!existing) {
      latestVersionBySource.set(version.source_id, version);
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

    return {
      source_id: source.source_id,
      name: source.name,
      totalRuns,
      failedRuns,
      successRate,
      lastRunDate,
      versionLabel: version?.version_label ?? null,
      versionStatus: version?.status ?? null,
    };
  });
}

export function SourceHealthCard() {
  const [sources, setSources] = useState<SourceItem[] | null>(null);
  const [runs, setRuns] = useState<RunItem[] | null>(null);
  const [versions, setVersions] = useState<SourceVersionItem[] | null>(null);
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

        // Fetch versions for each source
        const versionResults = await Promise.all(
          allSources.map(async (source) => {
            try {
              const res = await fetch(`${API_PREFIX}/v1/sources/${source.source_id}/versions`);
              if (!res.ok) return [];
              const body = (await res.json()) as { data: SourceVersionItem[] };
              return body.data;
            } catch {
              return [];
            }
          }),
        );

        if (cancelled) return;

        setSources(allSources);
        setRuns(recentRuns);
        setVersions(versionResults.flat());
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
      render: (row) => formatVersionInfo(row.versionLabel, row.versionStatus),
    },
  ];

  return (
    <Panel className="p-5">
      <SourceHealthHeader description="Per-source success rates from runs in the last 7 days. Click a row to inspect the source." />
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
