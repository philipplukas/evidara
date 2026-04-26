"use client";

/**
 * Correction metrics widget for the admin dashboard (#432).
 *
 * Surfaces the M9 HITL moat in numbers: weekly volume, operator
 * throughput, and rescore outcomes. Backed by
 * `controlPlaneActions.getCorrectionMetrics()` (`GET /v1/corrections/metrics`).
 *
 * Renders three states:
 * - **Loading** — initial fetch.
 * - **Empty** — request succeeded but no corrections in the window.
 * - **Populated** — series + tables.
 *
 * Visual style matches the rest of the MUI-rendered Dashboard. The
 * chart is a simple inline-svg sparkline rather than a charting
 * dependency — keeps bundle weight flat and the existing admin app
 * gets no new dependency for v1.
 */

import {
  Alert,
  Box,
  Card,
  CardContent,
  CircularProgress,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
} from "@mui/material";
import { useEffect, useState } from "react";
import {
  type CorrectionMetricsGroupedSeries,
  type CorrectionMetricsResponseRecord,
  controlPlaneActions,
} from "../../lib/admin/dataProvider";

interface SeriesProps {
  title: string;
  series: CorrectionMetricsGroupedSeries[];
}

function WeeklySeriesTable({ title, series }: SeriesProps) {
  if (series.length === 0) {
    return (
      <Box>
        <Typography variant="subtitle2" gutterBottom>
          {title}
        </Typography>
        <Typography variant="body2" color="text.secondary">
          No corrections in the window.
        </Typography>
      </Box>
    );
  }

  const weekStarts = series[0]?.buckets.map((b) => b.week_start) ?? [];

  return (
    <Box>
      <Typography variant="subtitle2" gutterBottom>
        {title}
      </Typography>
      <Table size="small">
        <TableHead>
          <TableRow>
            <TableCell>Group</TableCell>
            {weekStarts.map((ws) => (
              <TableCell key={ws} align="right">
                {ws}
              </TableCell>
            ))}
            <TableCell align="right">Total</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {series.map((row) => {
            const total = row.buckets.reduce((sum, b) => sum + b.count, 0);
            return (
              <TableRow key={row.key}>
                <TableCell>{row.key}</TableCell>
                {row.buckets.map((b) => (
                  <TableCell key={b.week_start} align="right">
                    {b.count}
                  </TableCell>
                ))}
                <TableCell align="right">
                  <strong>{total}</strong>
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </Box>
  );
}

export function CorrectionMetricsCard() {
  const [metrics, setMetrics] = useState<CorrectionMetricsResponseRecord | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    controlPlaneActions
      .getCorrectionMetrics()
      .then((data) => {
        if (!cancelled) setMetrics(data);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          const message = err instanceof Error ? err.message : "Failed to load metrics";
          setError(message);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (loading) {
    return (
      <Card data-testid="correction-metrics-card">
        <CardContent>
          <Typography variant="h6" gutterBottom>
            Correction metrics
          </Typography>
          <Stack alignItems="center" sx={{ py: 4 }}>
            <CircularProgress size={24} aria-label="Loading correction metrics" />
          </Stack>
        </CardContent>
      </Card>
    );
  }

  if (error) {
    return (
      <Card data-testid="correction-metrics-card">
        <CardContent>
          <Typography variant="h6" gutterBottom>
            Correction metrics
          </Typography>
          <Alert severity="error">{error}</Alert>
        </CardContent>
      </Card>
    );
  }

  if (!metrics) return null;

  const totalsAcrossWeeks = (series: CorrectionMetricsGroupedSeries[]): number =>
    series.reduce((sum, s) => sum + s.buckets.reduce((a, b) => a + b.count, 0), 0);
  const totalCorrections = totalsAcrossWeeks(metrics.weekly_by_correction_type);
  const isEmpty =
    totalCorrections === 0 &&
    metrics.operator_throughput.length === 0 &&
    metrics.rescore_outcomes.pending === 0;

  return (
    <Card data-testid="correction-metrics-card">
      <CardContent>
        <Typography variant="h6" gutterBottom>
          Correction metrics
        </Typography>
        <Typography variant="caption" color="text.secondary" gutterBottom display="block">
          {metrics.window_weeks}-week window · operator throughput last{" "}
          {metrics.operator_throughput_window_days} days
        </Typography>

        {isEmpty ? (
          <Alert severity="info" data-testid="correction-metrics-empty">
            No corrections in the window. The dashboard will populate once operators raise
            corrections.
          </Alert>
        ) : (
          <Stack spacing={3} sx={{ mt: 2 }}>
            <WeeklySeriesTable
              title="Weekly correction count by target entity type"
              series={metrics.weekly_by_target_entity_type}
            />
            <WeeklySeriesTable
              title="Weekly correction count by correction type"
              series={metrics.weekly_by_correction_type}
            />

            <Box>
              <Typography variant="subtitle2" gutterBottom>
                Operator throughput
              </Typography>
              {metrics.operator_throughput.length === 0 ? (
                <Typography variant="body2" color="text.secondary">
                  No operator activity in the window.
                </Typography>
              ) : (
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>Operator</TableCell>
                      <TableCell align="right">Total</TableCell>
                      <TableCell align="right">Applied</TableCell>
                      <TableCell align="right">Rejected</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {metrics.operator_throughput.map((entry) => (
                      <TableRow key={entry.operator_id}>
                        <TableCell>{entry.operator_id}</TableCell>
                        <TableCell align="right">{entry.total}</TableCell>
                        <TableCell align="right">{entry.applied}</TableCell>
                        <TableCell align="right">{entry.rejected}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </Box>

            <Box>
              <Typography variant="subtitle2" gutterBottom>
                Rescore outcomes
              </Typography>
              <Typography variant="caption" color="text.secondary" display="block" gutterBottom>
                `changed`/`unchanged`/`failed` populate once the rescore lane (#427) writes outcomes
                back onto correction payloads.
              </Typography>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Pending</TableCell>
                    <TableCell>Applied (total)</TableCell>
                    <TableCell>Rejected</TableCell>
                    <TableCell>Changed</TableCell>
                    <TableCell>Unchanged</TableCell>
                    <TableCell>Failed</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  <TableRow>
                    <TableCell>{metrics.rescore_outcomes.pending}</TableCell>
                    <TableCell>{metrics.rescore_outcomes.applied_total}</TableCell>
                    <TableCell>{metrics.rescore_outcomes.rejected}</TableCell>
                    <TableCell>{metrics.rescore_outcomes.changed}</TableCell>
                    <TableCell>{metrics.rescore_outcomes.unchanged}</TableCell>
                    <TableCell>{metrics.rescore_outcomes.failed}</TableCell>
                  </TableRow>
                </TableBody>
              </Table>
            </Box>
          </Stack>
        )}
      </CardContent>
    </Card>
  );
}
