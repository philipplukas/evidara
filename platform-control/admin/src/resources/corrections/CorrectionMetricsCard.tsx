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
 * Visual style matches the Tailwind-rendered Dashboard. The
 * chart is a simple inline-svg sparkline rather than a charting
 * dependency — keeps bundle weight flat and the existing admin app
 * gets no new dependency for v1.
 */

import { type ReactNode, useEffect, useState } from "react";
import {
  type CorrectionMetricsGroupedSeries,
  type CorrectionMetricsResponseRecord,
  controlPlaneActions,
} from "../../lib/admin/dataProvider";
import { InlineAlert, Panel, Spinner } from "../../ui/primitives";

interface SeriesProps {
  title: string;
  series: CorrectionMetricsGroupedSeries[];
}

function WeeklySeriesTable({ title, series }: SeriesProps) {
  if (series.length === 0) {
    return (
      <div>
        <h3 className="text-sm font-semibold text-[var(--foreground)]">{title}</h3>
        <p className="mt-1 text-sm text-[var(--text-muted)]">No corrections in the window.</p>
      </div>
    );
  }

  const weekStarts = series[0]?.buckets.map((b) => b.week_start) ?? [];

  return (
    <div>
      <h3 className="text-sm font-semibold text-[var(--foreground)]">{title}</h3>
      <div className="mt-2 overflow-x-auto rounded-lg border border-[var(--border)]">
        <table className="w-full border-collapse text-sm text-[var(--foreground)]">
          <thead className="bg-[var(--surface-input)]">
            <tr>
              <th className="border-b border-[var(--border)] px-4 py-3 text-left text-[12px] font-bold uppercase tracking-[0.08em] text-[var(--text-meta)]">
                Group
              </th>
              {weekStarts.map((ws) => (
                <th
                  key={ws}
                  className="border-b border-[var(--border)] px-4 py-3 text-right text-[12px] font-bold uppercase tracking-[0.08em] text-[var(--text-meta)]"
                >
                  {ws}
                </th>
              ))}
              <th className="border-b border-[var(--border)] px-4 py-3 text-right text-[12px] font-bold uppercase tracking-[0.08em] text-[var(--text-meta)]">
                Total
              </th>
            </tr>
          </thead>
          <tbody>
            {series.map((row) => {
              const total = row.buckets.reduce((sum, b) => sum + b.count, 0);
              return (
                <tr key={row.key} className="border-b border-[var(--border)] last:border-b-0">
                  <td className="px-4 py-3">{row.key}</td>
                  {row.buckets.map((b) => (
                    <td key={b.week_start} className="px-4 py-3 text-right tabular-nums">
                      {b.count}
                    </td>
                  ))}
                  <td className="px-4 py-3 text-right tabular-nums">
                    <strong>{total}</strong>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
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
      <Panel testId="correction-metrics-card" className="p-5">
        <CorrectionMetricsHeader />
        <div className="flex justify-center py-8">
          <Spinner label="Loading correction metrics" />
        </div>
      </Panel>
    );
  }

  if (error) {
    return (
      <Panel testId="correction-metrics-card" className="p-5">
        <CorrectionMetricsHeader />
        <InlineAlert tone="error" className="mt-4">
          {error}
        </InlineAlert>
      </Panel>
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
    <Panel testId="correction-metrics-card" className="p-5">
      <CorrectionMetricsHeader
        description={
          <>
            {metrics.window_weeks}-week window · operator throughput last{" "}
            {metrics.operator_throughput_window_days} days
          </>
        }
      />

      {isEmpty ? (
        <InlineAlert tone="info" testId="correction-metrics-empty" className="mt-4">
          No corrections in the window. The dashboard will populate once operators raise
          corrections.
        </InlineAlert>
      ) : (
        <div className="mt-5 space-y-6">
          <WeeklySeriesTable
            title="Weekly correction count by target entity type"
            series={metrics.weekly_by_target_entity_type}
          />
          <WeeklySeriesTable
            title="Weekly correction count by correction type"
            series={metrics.weekly_by_correction_type}
          />

          <div>
            <h3 className="text-sm font-semibold text-[var(--foreground)]">Operator throughput</h3>
            {metrics.operator_throughput.length === 0 ? (
              <p className="mt-1 text-sm text-[var(--text-muted)]">
                No operator activity in the window.
              </p>
            ) : (
              <div className="mt-2 overflow-x-auto rounded-lg border border-[var(--border)]">
                <table className="w-full border-collapse text-sm text-[var(--foreground)]">
                  <thead className="bg-[var(--surface-input)]">
                    <tr>
                      <MetricHead>Operator</MetricHead>
                      <MetricHead align="right">Total</MetricHead>
                      <MetricHead align="right">Applied</MetricHead>
                      <MetricHead align="right">Rejected</MetricHead>
                    </tr>
                  </thead>
                  <tbody>
                    {metrics.operator_throughput.map((entry) => (
                      <tr
                        key={entry.operator_id}
                        className="border-b border-[var(--border)] last:border-b-0"
                      >
                        <td className="px-4 py-3">{entry.operator_id}</td>
                        <MetricCell>{entry.total}</MetricCell>
                        <MetricCell>{entry.applied}</MetricCell>
                        <MetricCell>{entry.rejected}</MetricCell>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          <div>
            <h3 className="text-sm font-semibold text-[var(--foreground)]">Rescore outcomes</h3>
            <p className="mt-1 text-xs text-[var(--text-meta)]">
              `changed`/`unchanged`/`failed` populate once the rescore lane (#427) writes outcomes
              back onto correction payloads.
            </p>
            <div className="mt-2 overflow-x-auto rounded-lg border border-[var(--border)]">
              <table className="w-full border-collapse text-sm text-[var(--foreground)]">
                <thead className="bg-[var(--surface-input)]">
                  <tr>
                    <MetricHead>Pending</MetricHead>
                    <MetricHead>Applied (total)</MetricHead>
                    <MetricHead>Rejected</MetricHead>
                    <MetricHead>Changed</MetricHead>
                    <MetricHead>Unchanged</MetricHead>
                    <MetricHead>Failed</MetricHead>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <MetricCell align="left">{metrics.rescore_outcomes.pending}</MetricCell>
                    <MetricCell align="left">{metrics.rescore_outcomes.applied_total}</MetricCell>
                    <MetricCell align="left">{metrics.rescore_outcomes.rejected}</MetricCell>
                    <MetricCell align="left">{metrics.rescore_outcomes.changed}</MetricCell>
                    <MetricCell align="left">{metrics.rescore_outcomes.unchanged}</MetricCell>
                    <MetricCell align="left">{metrics.rescore_outcomes.failed}</MetricCell>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </Panel>
  );
}

function CorrectionMetricsHeader({ description }: { description?: ReactNode }) {
  return (
    <div>
      <h2 className="text-xl font-bold leading-tight text-[var(--foreground)]">
        Correction metrics
      </h2>
      {description ? <p className="mt-1 text-xs text-[var(--text-meta)]">{description}</p> : null}
    </div>
  );
}

function MetricHead({
  children,
  align = "left",
}: {
  children: ReactNode;
  align?: "left" | "right";
}) {
  return (
    <th
      className={`border-b border-[var(--border)] px-4 py-3 text-[12px] font-bold uppercase tracking-[0.08em] text-[var(--text-meta)] ${
        align === "right" ? "text-right" : "text-left"
      }`}
    >
      {children}
    </th>
  );
}

function MetricCell({
  children,
  align = "right",
}: {
  children: ReactNode;
  align?: "left" | "right";
}) {
  return (
    <td className={`px-4 py-3 tabular-nums ${align === "right" ? "text-right" : "text-left"}`}>
      {children}
    </td>
  );
}
