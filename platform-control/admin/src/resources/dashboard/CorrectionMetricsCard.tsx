/**
 * `CorrectionMetricsCard` — HITL-moat dashboard widget owned by #432.
 *
 * Reads the aggregate `/v1/corrections/metrics` read model and renders:
 *
 * 1. A row of summary stats (corrections / applied / rescores / unique
 *    operators) so the operator gets one-glance health.
 * 2. A weekly timeline table where each row decomposes a bucket into its
 *    correction-type counts, rescore-outcome bar, and per-week operator
 *    throughput (top 3 surfaced inline; full ranking lives in the
 *    sidebar leaderboard).
 *
 * The widget renders three states explicitly: loading, empty (zeroed
 * window — no corrections yet), and populated. Errors reuse the same
 * `Alert` pattern as the rest of the dashboard so the Sprint-3 visual
 * shorthand stays consistent.
 */
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
import { Activity, AlertTriangle, CheckCircle2, MinusCircle } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import {
  type CorrectionMetricsResponse,
  type CorrectionType,
  controlPlaneActions,
} from "../../lib/admin/dataProvider";
import { StatCard } from "../shared/Stat";
import {
  formatWeekLabel,
  isMetricsEmpty,
  METRICS_CORRECTION_TYPE_LABEL,
  percentOfTotal,
  summarizeMetrics,
  topOperators,
  weekTotal,
} from "./correctionMetrics";

const TYPE_ORDER: CorrectionType[] = ["field_edit", "annotation", "reject", "rescore_request"];

type CardState =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; data: CorrectionMetricsResponse };

function rescoreShare(
  outcomes: { changed: number; unchanged: number; failed: number },
  key: keyof typeof outcomes,
): number {
  const total = outcomes.changed + outcomes.unchanged + outcomes.failed;
  return percentOfTotal(outcomes[key], total);
}

export function CorrectionMetricsCard() {
  const [state, setState] = useState<CardState>({ kind: "loading" });

  useEffect(() => {
    let cancelled = false;
    setState({ kind: "loading" });

    controlPlaneActions
      .getCorrectionMetrics()
      .then((data) => {
        if (cancelled) return;
        setState({ kind: "ready", data });
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        const message =
          error instanceof Error ? error.message : "Unable to load correction metrics.";
        setState({ kind: "error", message });
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const summary = useMemo(() => {
    if (state.kind !== "ready") return null;
    return summarizeMetrics(state.data);
  }, [state]);

  const leaderboard = useMemo(() => {
    if (state.kind !== "ready") return [];
    return topOperators(state.data, 5);
  }, [state]);

  return (
    <Paper sx={{ p: 2.5 }} aria-labelledby="correction-metrics-heading">
      <Stack spacing={2}>
        <Box>
          <Typography
            id="correction-metrics-heading"
            variant="overline"
            sx={{
              letterSpacing: "0.14em",
              color: "text.secondary",
              lineHeight: 1.15,
            }}
          >
            HITL moat · Sprint 3
          </Typography>
          <Typography variant="h6" sx={{ mb: 0.5 }}>
            Correction metrics
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Weekly correction rate, operator throughput, and rescore outcomes — derived from
            <code> /v1/corrections/metrics</code>.
          </Typography>
        </Box>

        {state.kind === "loading" ? (
          <Stack direction="row" spacing={1.5} alignItems="center">
            <CircularProgress size={18} />
            <Typography variant="body2" color="text.secondary">
              Loading correction metrics…
            </Typography>
          </Stack>
        ) : state.kind === "error" ? (
          <Alert severity="warning" variant="outlined">
            {state.message}
          </Alert>
        ) : isMetricsEmpty(state.data) ? (
          <Alert severity="info" variant="outlined" icon={false}>
            <Stack direction="row" spacing={1.25} alignItems="flex-start">
              <Activity
                size={18}
                aria-hidden
                style={{ color: "var(--status-info, currentColor)", marginTop: 2 }}
              />
              <Box>
                <Typography variant="body2" sx={{ fontWeight: 600 }}>
                  No corrections recorded in the last 12 weeks.
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  Once an operator submits a correction this card will surface the rate, throughput,
                  and rescore outcomes per week.
                </Typography>
              </Box>
            </Stack>
          </Alert>
        ) : (
          <>
            <Stack direction={{ xs: "column", sm: "row" }} spacing={2} flexWrap="wrap">
              <StatCard label="Corrections" value={summary?.totalCorrections ?? 0} tone="info" />
              <StatCard label="Applied" value={summary?.totalApplied ?? 0} tone="success" />
              <StatCard label="Rescores" value={summary?.totalRescores ?? 0} tone="default" />
              <StatCard label="Operators" value={summary?.uniqueOperators ?? 0} tone="default" />
            </Stack>

            <Stack direction={{ xs: "column", lg: "row" }} spacing={2}>
              <Box sx={{ flex: 2, minWidth: 0 }}>
                <Table
                  size="small"
                  aria-label="Weekly correction breakdown"
                  sx={{
                    "& .MuiTableCell-head": {
                      backgroundColor: "rgba(244, 239, 231, 0.92)",
                      backdropFilter: "blur(10px)",
                    },
                  }}
                >
                  <TableHead>
                    <TableRow>
                      <TableCell>Week</TableCell>
                      <TableCell align="right">Total</TableCell>
                      <TableCell>By type</TableCell>
                      <TableCell>Rescore outcomes</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {state.data.weeks.map((week) => {
                      const total = weekTotal(week);
                      const outcomes = week.rescore_outcomes;
                      const rescoreTotal = outcomes.changed + outcomes.unchanged + outcomes.failed;
                      return (
                        <TableRow key={week.week_start}>
                          <TableCell>
                            <Stack spacing={0.25}>
                              <Typography variant="body2" sx={{ fontWeight: 600 }}>
                                {formatWeekLabel(week.week_start)}
                              </Typography>
                              <Typography
                                variant="caption"
                                color="text.secondary"
                                sx={{ fontFamily: "monospace" }}
                              >
                                {week.week_start}
                              </Typography>
                            </Stack>
                          </TableCell>
                          <TableCell align="right">
                            <Typography variant="body2" sx={{ fontVariantNumeric: "tabular-nums" }}>
                              {total}
                            </Typography>
                          </TableCell>
                          <TableCell>
                            {total === 0 ? (
                              <Typography variant="caption" color="text.secondary">
                                —
                              </Typography>
                            ) : (
                              <Stack direction="row" spacing={0.75} flexWrap="wrap">
                                {TYPE_ORDER.filter(
                                  (key) => (week.by_correction_type[key] ?? 0) > 0,
                                ).map((key) => (
                                  <Box
                                    key={key}
                                    sx={{
                                      display: "inline-flex",
                                      alignItems: "center",
                                      gap: 0.5,
                                      px: 1,
                                      py: 0.25,
                                      borderRadius: 999,
                                      backgroundColor: "var(--brand-wash-3)",
                                      color: "var(--foreground)",
                                      fontSize: 12,
                                      fontWeight: 600,
                                    }}
                                  >
                                    <span>{METRICS_CORRECTION_TYPE_LABEL[key]}</span>
                                    <span style={{ fontVariantNumeric: "tabular-nums" }}>
                                      {week.by_correction_type[key] ?? 0}
                                    </span>
                                  </Box>
                                ))}
                              </Stack>
                            )}
                          </TableCell>
                          <TableCell>
                            {rescoreTotal === 0 ? (
                              <Typography variant="caption" color="text.secondary">
                                no rescores
                              </Typography>
                            ) : (
                              <Stack direction="row" spacing={1} alignItems="center">
                                <Stack
                                  direction="row"
                                  spacing={0.5}
                                  alignItems="center"
                                  aria-label={`${outcomes.changed} changed`}
                                >
                                  <CheckCircle2
                                    size={14}
                                    aria-hidden
                                    style={{ color: "var(--status-healthy)" }}
                                  />
                                  <Typography
                                    variant="caption"
                                    sx={{ fontVariantNumeric: "tabular-nums" }}
                                  >
                                    {outcomes.changed}
                                  </Typography>
                                  <Typography variant="caption" color="text.secondary">
                                    ({rescoreShare(outcomes, "changed")}%)
                                  </Typography>
                                </Stack>
                                <Stack
                                  direction="row"
                                  spacing={0.5}
                                  alignItems="center"
                                  aria-label={`${outcomes.unchanged} unchanged`}
                                >
                                  <MinusCircle
                                    size={14}
                                    aria-hidden
                                    style={{ color: "var(--status-neutral)" }}
                                  />
                                  <Typography
                                    variant="caption"
                                    sx={{ fontVariantNumeric: "tabular-nums" }}
                                  >
                                    {outcomes.unchanged}
                                  </Typography>
                                </Stack>
                                <Stack
                                  direction="row"
                                  spacing={0.5}
                                  alignItems="center"
                                  aria-label={`${outcomes.failed} failed`}
                                >
                                  <AlertTriangle
                                    size={14}
                                    aria-hidden
                                    style={{ color: "var(--status-critical)" }}
                                  />
                                  <Typography
                                    variant="caption"
                                    sx={{ fontVariantNumeric: "tabular-nums" }}
                                  >
                                    {outcomes.failed}
                                  </Typography>
                                </Stack>
                              </Stack>
                            )}
                          </TableCell>
                        </TableRow>
                      );
                    })}
                  </TableBody>
                </Table>
              </Box>

              <Box sx={{ flex: 1, minWidth: 240 }}>
                <Typography variant="subtitle2" sx={{ mb: 1, fontWeight: 700 }}>
                  Top operators
                </Typography>
                {leaderboard.length === 0 ? (
                  <Typography variant="body2" color="text.secondary">
                    No applied corrections in this window yet.
                  </Typography>
                ) : (
                  <Stack spacing={0.75}>
                    {leaderboard.map((entry) => (
                      <Stack
                        key={entry.operator_id}
                        direction="row"
                        spacing={1}
                        alignItems="center"
                        justifyContent="space-between"
                        sx={{
                          px: 1.25,
                          py: 0.75,
                          borderRadius: 1,
                          backgroundColor: "var(--brand-wash-3)",
                        }}
                      >
                        <Typography
                          variant="body2"
                          sx={{
                            fontFamily: "monospace",
                            color: "var(--foreground)",
                            fontWeight: 600,
                          }}
                        >
                          {entry.operator_id}
                        </Typography>
                        <Typography
                          variant="body2"
                          sx={{ fontVariantNumeric: "tabular-nums", fontWeight: 600 }}
                        >
                          {entry.applied}
                        </Typography>
                      </Stack>
                    ))}
                  </Stack>
                )}
              </Box>
            </Stack>
          </>
        )}
      </Stack>
    </Paper>
  );
}
