"use client";

import {
  Box,
  Card,
  CardContent,
  Chip,
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
import { useEffect, useState } from "react";
import { useRedirect } from "react-admin";

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

const STATUS_COLORS: Record<string, "success" | "error" | "warning" | "info" | "default"> = {
  completed: "success",
  failed: "error",
  running: "info",
  pending: "warning",
  cancelled: "default",
};

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

function StatCard({ label, value }: { label: string; value: string | number }) {
  return (
    <Card sx={{ flex: 1, minWidth: 160 }}>
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

export function Dashboard() {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [loading, setLoading] = useState(true);
  const redirect = useRedirect();

  useEffect(() => {
    fetch("/api/platform-control/stats")
      .then((res) => res.json())
      .then(setStats)
      .catch(() => setStats(null))
      .finally(() => setLoading(false));
  }, []);

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

  return (
    <Box sx={{ p: 3 }}>
      <Typography variant="h5" sx={{ mb: 3 }}>
        Control Plane Overview
      </Typography>

      <Stack direction={{ xs: "column", sm: "row" }} spacing={2} sx={{ mb: 3 }}>
        <StatCard label="Sources" value={stats.source_count} />
        <StatCard label="Total Runs" value={stats.total_runs} />
        <StatCard label="Total Artifacts" value={stats.total_artifacts} />
        <StatCard label="Success Rate" value={successRate} />
      </Stack>

      <Stack direction={{ xs: "column", md: "row" }} spacing={2} sx={{ mb: 3 }}>
        <Paper sx={{ flex: 1, p: 2 }}>
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
      </Stack>

      <Paper sx={{ p: 2 }}>
        <Typography variant="h6" sx={{ mb: 1 }}>
          Recent Runs
        </Typography>
        {stats.recent_runs.length > 0 ? (
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Run ID</TableCell>
                <TableCell>Status</TableCell>
                <TableCell>Artifacts</TableCell>
                <TableCell>Created</TableCell>
                <TableCell>Duration</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {stats.recent_runs.map((run) => (
                <TableRow
                  key={run.run_id}
                  hover
                  sx={{ cursor: "pointer" }}
                  onClick={() => redirect("show", "runs", run.run_id)}
                >
                  <TableCell>
                    <Typography variant="caption" sx={{ fontFamily: "monospace" }}>
                      {run.run_id}
                    </Typography>
                  </TableCell>
                  <TableCell>
                    <Chip
                      size="small"
                      label={run.status}
                      color={STATUS_COLORS[run.status] ?? "default"}
                    />
                  </TableCell>
                  <TableCell>{run.artifacts_count}</TableCell>
                  <TableCell>{formatTime(run.created_at)}</TableCell>
                  <TableCell>{formatDuration(run.created_at, run.completed_at)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ) : (
          <Typography variant="body2" color="text.secondary">
            No runs found. Create a source and trigger a run to get started.
          </Typography>
        )}
      </Paper>
    </Box>
  );
}
