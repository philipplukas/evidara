"use client";

import {
  Alert,
  Box,
  Button,
  Card,
  CardActions,
  CardContent,
  Chip,
  CircularProgress,
  Divider,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
} from "@mui/material";
import { type ReactNode, useEffect, useState } from "react";
import { useRedirect } from "react-admin";
import type { RunPipelineHealth } from "../../lib/admin/dataProvider";
import { controlPlaneActions } from "../../lib/admin/dataProvider";
import { RunLaunchButton } from "../runs/RunLaunchDialog";

type DashboardStats = {
  source_count: number;
  total_runs: number;
  run_by_status: Record<string, number>;
  total_artifacts: number;
  recent_runs: Array<{
    run_id: string;
    status: string;
    artifacts_count: number;
    created_at: string | null;
    completed_at: string | null;
  }>;
};

type RecentRunHealth = {
  run_id: string;
  health: RunPipelineHealth | null;
  error: string | null;
};

const STATUS_COLORS: Record<string, "success" | "error" | "warning" | "info" | "default"> = {
  completed: "success",
  failed: "error",
  running: "info",
  pending: "warning",
  cancelled: "default",
};

const HEALTH_COLORS: Record<string, "success" | "error" | "warning" | "info" | "default"> = {
  ok: "success",
  blocked: "warning",
  failed: "error",
  in_progress: "info",
};

const MAX_HEALTH_PROBES = 5;

const formatDuration = (start: string | null, end: string | null): string => {
  if (!start || !end) return "-";
  const ms = new Date(end).getTime() - new Date(start).getTime();
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  return `${Math.floor(ms / 60000)}m ${Math.round((ms % 60000) / 1000)}s`;
};

const formatTime = (value: string | null): string => {
  if (!value) return "-";
  return new Intl.DateTimeFormat("en", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
};

function StatCard({
  label,
  value,
  tone = "default",
}: {
  label: string;
  value: string | number;
  tone?: "success" | "error" | "warning" | "info" | "default";
}) {
  return (
    <Card
      sx={{
        flex: 1,
        minWidth: 160,
        borderColor:
          tone === "default"
            ? "rgba(29, 41, 61, 0.08)"
            : `rgba(${tone === "success" ? "25, 118, 210" : tone === "error" ? "211, 47, 47" : tone === "warning" ? "237, 108, 2" : "2, 136, 209"}, 0.16)`,
      }}
    >
      <CardContent sx={{ textAlign: "center", py: 3 }}>
        <Typography variant="h4" sx={{ fontWeight: 700, mb: 0.5 }}>
          {value}
        </Typography>
        <Typography variant="body2" color="text.secondary">
          {label}
        </Typography>
      </CardContent>
    </Card>
  );
}

function ActionCard({
  eyebrow,
  title,
  description,
  action,
  tone = "default",
}: {
  eyebrow: string;
  title: string;
  description: string;
  action: ReactNode;
  tone?: "success" | "error" | "warning" | "info" | "default";
}) {
  return (
    <Card
      sx={{
        flex: 1,
        minWidth: 240,
        borderTop: "4px solid",
        borderTopColor:
          tone === "success"
            ? "success.main"
            : tone === "error"
              ? "error.main"
              : tone === "warning"
                ? "warning.main"
                : tone === "info"
                  ? "info.main"
                  : "divider",
      }}
    >
      <CardContent sx={{ display: "flex", flexDirection: "column", gap: 1.25, minHeight: 184 }}>
        <Typography
          variant="overline"
          sx={{
            letterSpacing: "0.14em",
            color: "text.secondary",
            lineHeight: 1.15,
          }}
        >
          {eyebrow}
        </Typography>
        <Typography variant="h6" sx={{ fontWeight: 700, lineHeight: 1.15 }}>
          {title}
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ flex: 1 }}>
          {description}
        </Typography>
        <CardActions sx={{ px: 0, pb: 0 }}>{action}</CardActions>
      </CardContent>
    </Card>
  );
}

export function Dashboard() {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [recentHealth, setRecentHealth] = useState<RecentRunHealth[]>([]);
  const [healthLoading, setHealthLoading] = useState(false);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const redirect = useRedirect();

  useEffect(() => {
    fetch("/api/platform-control/stats")
      .then((res) => res.json())
      .then(setStats)
      .catch(() => setStats(null))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (!stats?.recent_runs.length) {
      setRecentHealth([]);
      setHealthError(null);
      setHealthLoading(false);
      return;
    }

    const probeRuns = stats.recent_runs.slice(0, MAX_HEALTH_PROBES);
    let cancelled = false;

    setHealthLoading(true);
    setHealthError(null);

    void Promise.all(
      probeRuns.map(async (run) => {
        try {
          const health = await controlPlaneActions.getRunPipelineHealth(run.run_id);
          return { run_id: run.run_id, health, error: null } satisfies RecentRunHealth;
        } catch (error) {
          return {
            run_id: run.run_id,
            health: null,
            error: error instanceof Error ? error.message : "Unable to load pipeline health.",
          } satisfies RecentRunHealth;
        }
      }),
    )
      .then((items) => {
        if (!cancelled) {
          setRecentHealth(items);
        }
      })
      .catch((error) => {
        if (!cancelled) {
          setHealthError(error instanceof Error ? error.message : "Unable to load run health.");
        }
      })
      .finally(() => {
        if (!cancelled) {
          setHealthLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [stats?.recent_runs]);

  if (loading) {
    return (
      <Box sx={{ display: "flex", justifyContent: "center", py: 8 }}>
        <CircularProgress />
      </Box>
    );
  }

  if (!stats) {
    return (
      <Box sx={{ p: 3 }}>
        <Typography color="error">Unable to load dashboard stats.</Typography>
      </Box>
    );
  }

  const completed = stats.run_by_status.completed ?? 0;
  const failed = stats.run_by_status.failed ?? 0;
  const successRate =
    completed + failed > 0 ? `${Math.round((completed / (completed + failed)) * 100)}%` : "-";
  const recentHealthSummary = recentHealth.reduce(
    (summary, entry) => {
      if (!entry.health) {
        summary.unavailable += 1;
        return summary;
      }

      summary[entry.health.overall_status] += 1;
      return summary;
    },
    { ok: 0, blocked: 0, failed: 0, in_progress: 0, unavailable: 0 },
  );
  const attentionRun = (() => {
    const blockedRun = recentHealth.find((entry) => entry.health?.overall_status === "blocked");
    if (blockedRun) {
      return {
        run_id: blockedRun.run_id,
        reason: "blocked pipeline health",
      };
    }

    const failedRun = recentHealth.find((entry) => entry.health?.overall_status === "failed");
    if (failedRun) {
      return {
        run_id: failedRun.run_id,
        reason: "failed pipeline health",
      };
    }

    const blockedStatusRun = stats.recent_runs.find((run) =>
      ["failed", "pending", "running"].includes(run.status),
    );
    if (blockedStatusRun) {
      return {
        run_id: blockedStatusRun.run_id,
        reason:
          blockedStatusRun.status === "failed"
            ? "failed run status"
            : blockedStatusRun.status === "pending"
              ? "pending run status"
              : "active run status",
      };
    }

    return null;
  })();

  return (
    <Box sx={{ p: { xs: 2, md: 3 } }}>
      <Stack spacing={3}>
        <Paper
          sx={{
            p: { xs: 2.25, md: 3 },
            overflow: "hidden",
            position: "relative",
            background:
              "linear-gradient(145deg, rgba(15, 76, 129, 0.06), rgba(154, 122, 74, 0.05) 60%, rgba(255, 253, 248, 0.92))",
          }}
        >
          <Stack spacing={2.25}>
            <Box>
              <Typography
                variant="overline"
                sx={{
                  letterSpacing: "0.18em",
                  color: "text.secondary",
                  lineHeight: 1.15,
                }}
              >
                Operator command center
              </Typography>
              <Typography variant="h5" sx={{ fontWeight: 700, mt: 0.5 }}>
                Control Plane Overview
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ maxWidth: 760, mt: 0.75 }}>
                Launch work, pick up the newest blocked run, and keep the recent pipeline health in
                view without leaving the overview.
              </Typography>
            </Box>

            <Stack direction={{ xs: "column", lg: "row" }} spacing={2}>
              <ActionCard
                eyebrow="Primary action"
                title="Create a run"
                description="Start a new production run from the same operator surface used to inspect and triage existing work."
                tone="info"
                action={
                  <RunLaunchButton
                    label="Create Run"
                    defaultMode="production"
                    redirectResource="runs"
                  />
                }
              />
              <ActionCard
                eyebrow="Attention"
                title="Inspect blocked run"
                description={
                  attentionRun
                    ? `Open ${attentionRun.run_id} first. It is the newest run with ${attentionRun.reason}.`
                    : "No blocked or stalled run is visible yet. Recent runs are all complete or unavailable."
                }
                tone={attentionRun ? "warning" : "default"}
                action={
                  <Button
                    variant="outlined"
                    color="warning"
                    disabled={!attentionRun}
                    onClick={() => {
                      if (attentionRun) {
                        redirect("show", "runs", attentionRun.run_id);
                      }
                    }}
                  >
                    {attentionRun ? "Inspect blocked run" : "No blocked run"}
                  </Button>
                }
              />
              <ActionCard
                eyebrow="Queue"
                title="Open run queue"
                description="Switch to the list view when you want the full operator queue, then filter by state to clear the next item."
                tone="info"
                action={
                  <Button variant="outlined" onClick={() => redirect("list", "runs")}>
                    Open queue
                  </Button>
                }
              />
            </Stack>

            <Stack direction={{ xs: "column", sm: "row" }} spacing={2} flexWrap="wrap">
              <StatCard label="Sources" value={stats.source_count} />
              <StatCard label="Total Runs" value={stats.total_runs} />
              <StatCard label="Total Artifacts" value={stats.total_artifacts} />
              <StatCard
                label="Success Rate"
                value={successRate}
                tone={successRate === "-" ? "default" : "success"}
              />
            </Stack>
          </Stack>
        </Paper>

        <Stack direction={{ xs: "column", xl: "row" }} spacing={2}>
          <Paper sx={{ flex: 1, p: 2.5 }}>
            <Typography variant="h6" sx={{ mb: 1 }}>
              Runs by Status
            </Typography>
            <Stack direction="row" spacing={1} flexWrap="wrap">
              {Object.entries(stats.run_by_status).map(([status, count]) => (
                <Chip
                  key={status}
                  label={`${status}: ${count}`}
                  color={STATUS_COLORS[status] ?? "default"}
                  variant="outlined"
                  size="small"
                />
              ))}
              {Object.keys(stats.run_by_status).length === 0 && (
                <Typography variant="body2" color="text.secondary">
                  No runs yet.
                </Typography>
              )}
            </Stack>
          </Paper>

          <Paper sx={{ flex: 1, p: 2.5 }}>
            <Typography variant="h6" sx={{ mb: 1 }}>
              Recent health snapshot
            </Typography>
            {healthLoading ? (
              <Stack direction="row" spacing={1.5} alignItems="center">
                <CircularProgress size={18} />
                <Typography variant="body2" color="text.secondary">
                  Loading pipeline health...
                </Typography>
              </Stack>
            ) : healthError ? (
              <Alert severity="warning">{healthError}</Alert>
            ) : (
              <Stack direction="row" spacing={1} flexWrap="wrap">
                <Chip
                  label={`ok: ${recentHealthSummary.ok}`}
                  color="success"
                  variant="outlined"
                  size="small"
                />
                <Chip
                  label={`blocked: ${recentHealthSummary.blocked}`}
                  color="warning"
                  variant="outlined"
                  size="small"
                />
                <Chip
                  label={`failed: ${recentHealthSummary.failed}`}
                  color="error"
                  variant="outlined"
                  size="small"
                />
                <Chip
                  label={`in progress: ${recentHealthSummary.in_progress}`}
                  color="info"
                  variant="outlined"
                  size="small"
                />
                <Chip
                  label={`unavailable: ${recentHealthSummary.unavailable}`}
                  variant="outlined"
                  size="small"
                />
              </Stack>
            )}
          </Paper>
        </Stack>

        <Paper id="recent-run-health" sx={{ p: 2.5 }}>
          <Stack spacing={2}>
            <Box>
              <Typography variant="h6" sx={{ mb: 0.5 }}>
                Recent Runs
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Newest runs stay in view here. Click a row to inspect the full run, or use the
                status chips above to prioritize the queue.
              </Typography>
            </Box>

            {stats.recent_runs.length > 0 ? (
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Run</TableCell>
                    <TableCell>Status</TableCell>
                    <TableCell>Artifacts</TableCell>
                    <TableCell>Created</TableCell>
                    <TableCell>Duration</TableCell>
                    <TableCell align="right">Inspect</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {stats.recent_runs.map((run) => {
                    const health = recentHealth.find(
                      (entry) => entry.run_id === run.run_id,
                    )?.health;
                    const healthTone =
                      health?.overall_status === "ok"
                        ? "success"
                        : health?.overall_status === "blocked"
                          ? "warning"
                          : health?.overall_status === "failed"
                            ? "error"
                            : health?.overall_status === "in_progress"
                              ? "info"
                              : "default";

                    return (
                      <TableRow
                        key={run.run_id}
                        hover
                        sx={{ cursor: "pointer" }}
                        onClick={() => redirect("show", "runs", run.run_id)}
                      >
                        <TableCell>
                          <Stack spacing={0.25}>
                            <Typography variant="body2" sx={{ fontFamily: "monospace" }}>
                              {run.run_id}
                            </Typography>
                            <Typography variant="caption" color="text.secondary">
                              {health?.overall_status ?? "pipeline health unavailable"}
                            </Typography>
                          </Stack>
                        </TableCell>
                        <TableCell>
                          <Stack direction="row" spacing={1} alignItems="center">
                            <Chip
                              size="small"
                              label={run.status}
                              color={STATUS_COLORS[run.status] ?? "default"}
                            />
                            {health ? (
                              <Chip
                                size="small"
                                label={health.overall_status}
                                color={HEALTH_COLORS[health.overall_status] ?? "default"}
                                variant="outlined"
                              />
                            ) : null}
                          </Stack>
                        </TableCell>
                        <TableCell>{run.artifacts_count}</TableCell>
                        <TableCell>{formatTime(run.created_at)}</TableCell>
                        <TableCell>{formatDuration(run.created_at, run.completed_at)}</TableCell>
                        <TableCell align="right">
                          <Button
                            size="small"
                            variant="text"
                            color={healthTone === "warning" ? "warning" : "inherit"}
                            onClick={(event) => {
                              event.stopPropagation();
                              redirect("show", "runs", run.run_id);
                            }}
                          >
                            Inspect
                          </Button>
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            ) : (
              <Typography variant="body2" color="text.secondary">
                No runs found. Create a source and trigger a run to get started.
              </Typography>
            )}
          </Stack>
        </Paper>

        <Divider />
      </Stack>
    </Box>
  );
}
