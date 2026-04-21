"use client";

import {
  Alert,
  Box,
  CircularProgress,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
} from "@mui/material";
import { useEffect, useMemo, useState } from "react";
import { useRedirect } from "react-admin";
import { ResourceName } from "../../domain/resourceNames";
import { formatSwissDateTime } from "../../lib/format/date";

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

const STATUS_DOT_COLORS: Record<StatusDotLevel, string> = {
  healthy: "var(--status-healthy)",
  degraded: "var(--status-degraded)",
  critical: "var(--status-critical)",
  neutral: "var(--status-neutral)",
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
      completedOrFailed > 0
        ? ((completedOrFailed - failedRuns) / completedOrFailed) * 100
        : null;

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
              const res = await fetch(
                `${API_PREFIX}/v1/sources/${source.source_id}/versions`,
              );
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
      <Paper sx={{ p: 2.5 }}>
        <Stack spacing={1.5}>
          <Box>
            <Typography variant="h6" sx={{ mb: 0.5 }}>
              Source Health
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Loading source health scorecard...
            </Typography>
          </Box>
          <Stack direction="row" spacing={1.5} alignItems="center">
            <CircularProgress size={18} />
            <Typography variant="body2" color="text.secondary">
              Fetching sources and recent runs...
            </Typography>
          </Stack>
        </Stack>
      </Paper>
    );
  }

  if (error) {
    return (
      <Paper sx={{ p: 2.5 }}>
        <Stack spacing={1.5}>
          <Typography variant="h6">Source Health</Typography>
          <Alert severity="warning" variant="outlined">
            {error}
          </Alert>
        </Stack>
      </Paper>
    );
  }

  return (
    <Paper sx={{ p: 2.5 }}>
      <Stack spacing={2}>
        <Box>
          <Typography variant="h6" sx={{ mb: 0.5 }}>
            Source Health
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Per-source success rates from runs in the last 7 days. Click a row to inspect the
            source.
          </Typography>
        </Box>

        {healthRows.length > 0 ? (
          <Table
            size="small"
            stickyHeader
            sx={{
              "& .MuiTableCell-head": {
                backgroundColor: "rgba(244, 239, 231, 0.92)",
                backdropFilter: "blur(10px)",
              },
              "& .MuiTableRow-root:hover": {
                backgroundColor: "var(--brand-wash-3)",
              },
            }}
          >
            <TableHead>
              <TableRow>
                <TableCell>Source Name</TableCell>
                <TableCell>Status</TableCell>
                <TableCell>Success Rate</TableCell>
                <TableCell>Last Run</TableCell>
                <TableCell>Version</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {healthRows.map((row) => {
                const level = deriveStatusLevel(row.successRate);
                return (
                  <TableRow
                    key={row.source_id}
                    hover
                    sx={{ cursor: "pointer" }}
                    onClick={() => redirect("show", ResourceName.Sources, row.source_id)}
                  >
                    <TableCell>
                      <Typography variant="body2" sx={{ fontWeight: 600 }}>
                        {row.name}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Stack direction="row" spacing={0.75} alignItems="center">
                        <Box
                          component="span"
                          sx={{
                            width: 10,
                            height: 10,
                            borderRadius: "50%",
                            backgroundColor: STATUS_DOT_COLORS[level],
                            display: "inline-block",
                            flexShrink: 0,
                          }}
                        />
                        <Typography variant="body2">{STATUS_DOT_LABELS[level]}</Typography>
                      </Stack>
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2">
                        {formatSuccessRate(row.totalRuns, row.failedRuns, row.successRate)}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2">
                        {formatRelativeTime(row.lastRunDate)}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2">
                        {formatVersionInfo(row.versionLabel, row.versionStatus)}
                      </Typography>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        ) : (
          <Typography variant="body2" color="text.secondary">
            No sources found. Create a source to see health data here.
          </Typography>
        )}
      </Stack>
    </Paper>
  );
}
