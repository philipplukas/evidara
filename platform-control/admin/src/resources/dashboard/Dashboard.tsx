"use client";

import { type CSSProperties, type ReactNode, useEffect, useState } from "react";
import { useRedirect } from "react-admin";
import { ResourceName } from "../../domain/resourceNames";
import type { RunPipelineHealth } from "../../lib/admin/dataProvider";
import { controlPlaneActions } from "../../lib/admin/dataProvider";
import { formatSwissDateTime } from "../../lib/format/date";
import {
  Button,
  DataTable,
  type DataTableColumn,
  InlineAlert,
  Panel,
  Pill,
  Spinner,
} from "../../ui/primitives";
import { CorrectionMetricsCard } from "../corrections/CorrectionMetricsCard";
import { RunLaunchButton } from "../runs/RunLaunchDialog";
import { StatCard, type StatTone, statToneBorder, successRateTone } from "../shared/Stat";
import { pipelineHealthToLevel, runRecordStatusToLevel } from "../shared/statusLevels";
import { SourceHealthCard } from "./SourceHealthCard";

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
    started_at: string | null;
    completed_at: string | null;
  }>;
};

/**
 * `/stats` is only usable if it actually carries the counters the dashboard
 * reads. A bare `res.json()` was not enough (#623): FastAPI's 500 returns valid
 * JSON (`{"detail": "Internal Server Error"}`), so the parse resolved, the
 * truthy object slipped past the `if (!stats)` guard, and `stats.run_by_status`
 * threw — taking down the whole SPA through react-admin's error boundary. A
 * healthy `200 {}` did the same. Anything that is not a well-formed payload is
 * mapped to `null`, which is what the InlineAlert branch renders.
 */
const isDashboardStats = (payload: unknown): payload is DashboardStats => {
  if (typeof payload !== "object" || payload === null) {
    return false;
  }
  const candidate = payload as Partial<DashboardStats>;
  return (
    typeof candidate.source_count === "number" &&
    typeof candidate.total_runs === "number" &&
    typeof candidate.total_artifacts === "number" &&
    typeof candidate.run_by_status === "object" &&
    candidate.run_by_status !== null &&
    Array.isArray(candidate.recent_runs)
  );
};

/**
 * Fetch the dashboard counters, resolving to `null` for every failure mode —
 * non-2xx, unparseable body, well-formed JSON of the wrong shape, and network
 * error. Exported so the failure modes can be tested without mounting the
 * react-admin tree.
 */
export const loadDashboardStats = async (): Promise<DashboardStats | null> => {
  try {
    const response = await fetch("/api/platform-control/stats");
    if (!response.ok) {
      return null;
    }
    const payload: unknown = await response.json();
    return isDashboardStats(payload) ? payload : null;
  } catch {
    return null;
  }
};

type RecentRunHealth = {
  run_id: string;
  health: RunPipelineHealth | null;
  error: string | null;
};

type RecentHealthSummary = {
  ok: number;
  blocked: number;
  failed: number;
  in_progress: number;
  unavailable: number;
};

/**
 * The `overall_status` values this dashboard has a bucket for.
 *
 * The contract types `RunPipelineHealthResponse.overall_status` as an open
 * `string`, not an enum — the admin used to hand-declare it as a four-member
 * union, which was narrower than what the server may send (#695). An
 * unrecognised status counts as `unavailable` rather than silently landing in
 * whichever bucket it happens to spell.
 */
const HEALTH_BUCKETS = ["ok", "blocked", "failed", "in_progress"] as const;

type HealthBucket = (typeof HEALTH_BUCKETS)[number];

const isHealthBucket = (value: string): value is HealthBucket =>
  (HEALTH_BUCKETS as readonly string[]).includes(value);

/**
 * What the ATTENTION card should point the operator at.
 *
 * `run`   — we have an actual run id worth opening.
 * `queue` — the counters say work needs attention but the recent window does
 *           not contain it, so the honest answer is "go look at the filtered
 *           queue", not "nothing needs attention".
 */
export type AttentionTarget =
  | { kind: "run"; run_id: string; reason: string }
  | { kind: "queue"; status: "failed" | "pending" | "running"; count: number; reason: string };

const MAX_HEALTH_PROBES = 5;

export const formatDuration = (start: string | null, end: string | null): string => {
  if (!start || !end) return "-";
  const ms = new Date(end).getTime() - new Date(start).getTime();
  // Clock skew between the writers of `started_at`/`completed_at` can land the
  // end before the start (seen live on the ZH repro run: completed_at was 1ms
  // before created_at, rendering a confident "-1ms"). A negative elapsed time
  // is not a duration we know — say so rather than print an impossible number.
  if (!Number.isFinite(ms) || ms < 0) return "-";
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  return `${Math.floor(ms / 60000)}m ${Math.round((ms % 60000) / 1000)}s`;
};

const formatTime = (value: string | null): string => formatSwissDateTime(value) || "-";

export const summarizeRecentHealth = (recentHealth: RecentRunHealth[]): RecentHealthSummary =>
  recentHealth.reduce(
    (summary, entry) => {
      if (!entry.health) {
        summary.unavailable += 1;
        return summary;
      }

      const key = entry.health.overall_status;
      if (isHealthBucket(key)) {
        summary[key] += 1;
      } else {
        summary.unavailable += 1;
      }
      return summary;
    },
    { ok: 0, blocked: 0, failed: 0, in_progress: 0, unavailable: 0 },
  );

/**
 * Pick what the ATTENTION card should point at.
 *
 * The bug this fixes (#670): the selector scanned only `stats.recent_runs`,
 * which `/stats` caps at 5. The failed ADR-0033 dog-axis run was 11th by
 * recency, so the card rendered "No blocked or stalled run is visible yet" on
 * the same screen that showed `failed: 1` — a conclusion drawn from a truncated
 * list, presented as an answer about the whole system.
 *
 * `runByStatus` is the counter over *all* runs and comes from the same `/stats`
 * payload, so consulting it costs nothing and is the only way this function can
 * distinguish "nothing needs attention" from "the thing that needs attention is
 * outside my window". The disabled/empty state is now reachable only when the
 * counters actually say zero.
 */
export const selectDashboardAttentionRun = (
  recentHealth: RecentRunHealth[],
  recentRuns: DashboardStats["recent_runs"],
  runByStatus: Record<string, number> = {},
): AttentionTarget | null => {
  const blockedRun = recentHealth.find((entry) => entry.health?.overall_status === "blocked");
  if (blockedRun) {
    return {
      kind: "run",
      run_id: blockedRun.run_id,
      reason: "blocked pipeline health",
    };
  }

  const failedRun = recentHealth.find((entry) => entry.health?.overall_status === "failed");
  if (failedRun) {
    return {
      kind: "run",
      run_id: failedRun.run_id,
      reason: "failed pipeline health",
    };
  }

  const blockedStatusRun = recentRuns.find((run) =>
    ["failed", "pending", "running"].includes(run.status),
  );
  if (blockedStatusRun) {
    return {
      kind: "run",
      run_id: blockedStatusRun.run_id,
      reason:
        blockedStatusRun.status === "failed"
          ? "failed run status"
          : blockedStatusRun.status === "pending"
            ? "pending run status"
            : "active run status",
    };
  }

  // Nothing actionable in the recent window — but the counters may still know
  // better. Failed first: it is the only one that is unambiguously wrong.
  const outsideWindow: Array<{ status: "failed" | "pending" | "running"; reason: string }> = [
    { status: "failed", reason: "failed" },
    { status: "pending", reason: "pending" },
    { status: "running", reason: "running" },
  ];
  for (const candidate of outsideWindow) {
    const count = runByStatus[candidate.status] ?? 0;
    if (count > 0) {
      return {
        kind: "queue",
        status: candidate.status,
        count,
        reason: candidate.reason,
      };
    }
  }

  return null;
};

/** Card copy for whatever `selectDashboardAttentionRun` returned. */
export const describeAttentionTarget = (
  target: AttentionTarget | null,
): { description: string; buttonLabel: string } => {
  if (!target) {
    return {
      description:
        "No run is failing, pending, or running. The run counters — not just the recent five — report nothing needing attention.",
      buttonLabel: "No blocked run",
    };
  }

  if (target.kind === "run") {
    return {
      description: `Open ${target.run_id} first. It is the newest run with ${target.reason}.`,
      buttonLabel: "Inspect blocked run",
    };
  }

  const plural = target.count === 1 ? "run" : "runs";
  return {
    description: `${target.count} ${target.reason} ${plural} exist but fall outside the five most recent, so no id is shown here. Open the filtered queue to triage them.`,
    buttonLabel: `Open ${target.reason} queue`,
  };
};

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
  tone?: StatTone;
}) {
  return (
    <Panel
      className="flex min-w-60 flex-1 flex-col border-t-4 p-5"
      style={{ borderTopColor: statToneBorder(tone) } as CSSProperties}
    >
      <div className="flex min-h-44 flex-1 flex-col gap-3">
        <span className="text-[11px] font-semibold uppercase tracking-[0.14em] leading-[1.15] text-[var(--text-meta)]">
          {eyebrow}
        </span>
        <h3 className="text-xl font-bold leading-tight text-[var(--foreground)]">{title}</h3>
        <p className="flex-1 text-sm leading-snug text-[var(--text-muted)]">{description}</p>
        <div>{action}</div>
      </div>
    </Panel>
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
    let cancelled = false;
    void loadDashboardStats().then((payload) => {
      if (cancelled) {
        return;
      }
      setStats(payload);
      setLoading(false);
    });
    return () => {
      cancelled = true;
    };
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
      <div className="flex justify-center py-8">
        <Spinner label="Loading dashboard..." />
      </div>
    );
  }

  if (!stats) {
    return (
      <div className="p-6">
        <InlineAlert tone="error">Unable to load dashboard stats.</InlineAlert>
      </div>
    );
  }

  const completed = stats.run_by_status.completed ?? 0;
  const failed = stats.run_by_status.failed ?? 0;
  const successRate =
    completed + failed > 0 ? `${Math.round((completed / (completed + failed)) * 100)}%` : "-";
  const recentHealthSummary = summarizeRecentHealth(recentHealth);
  const attentionRun = selectDashboardAttentionRun(
    recentHealth,
    stats.recent_runs,
    stats.run_by_status,
  );
  const attentionCopy = describeAttentionTarget(attentionRun);
  const recentRunColumns: DataTableColumn<DashboardStats["recent_runs"][number]>[] = [
    {
      key: "run",
      header: "Run",
      render: (run) => {
        const health = recentHealth.find((entry) => entry.run_id === run.run_id)?.health;
        return (
          <div className="space-y-0.5">
            <span className="block font-mono text-sm">{run.run_id}</span>
            <span className="block text-xs text-[var(--text-meta)]">
              {health?.overall_status ?? "pipeline health unavailable"}
            </span>
          </div>
        );
      },
    },
    {
      key: "status",
      header: "Status",
      render: (run) => {
        const health = recentHealth.find((entry) => entry.run_id === run.run_id)?.health;
        return (
          <div className="flex flex-wrap items-center gap-2">
            <Pill level={runRecordStatusToLevel(run.status)}>{run.status}</Pill>
            {health ? (
              <Pill level={pipelineHealthToLevel(health.overall_status)}>
                {health.overall_status}
              </Pill>
            ) : null}
          </div>
        );
      },
    },
    {
      key: "artifacts",
      header: "Artifacts",
      render: (run) => <span className="tabular-nums">{run.artifacts_count}</span>,
    },
    {
      key: "created",
      header: "Created",
      render: (run) => formatTime(run.created_at),
    },
    {
      key: "duration",
      header: "Duration",
      // `created_at -> completed_at` is queue wait + execution, not a duration.
      // Three Fedlex runs read "2m 20s" here while the run detail page read
      // "273ms" for the same run under the same column name (#674). Measure what
      // the detail page measures: `started_at -> completed_at`. A run that never
      // started has no duration to state, and formatDuration renders "-".
      render: (run) => formatDuration(run.started_at, run.completed_at),
    },
    {
      key: "inspect",
      header: "Inspect",
      headerClassName: "text-right",
      className: "text-right",
      render: (run) => (
        <Button
          size="sm"
          variant="ghost"
          onClick={(event) => {
            event.stopPropagation();
            redirect("show", ResourceName.Runs, run.run_id);
          }}
        >
          Inspect
        </Button>
      ),
    },
  ];

  return (
    <div className="p-4 md:p-6">
      <div className="space-y-6">
        <Panel className="overflow-hidden bg-[linear-gradient(145deg,var(--brand-wash-6),var(--admin-panel-bg))] p-5 md:p-6">
          <div className="space-y-6">
            <div>
              <span className="text-[11px] font-semibold uppercase tracking-[0.18em] leading-[1.15] text-[var(--text-meta)]">
                Operator command center
              </span>
              <h1 className="mt-2 font-[family:var(--font-admin-serif)] text-2xl font-semibold leading-tight text-[var(--foreground)]">
                Control plane overview
              </h1>
              <p className="mt-2 max-w-[760px] text-sm leading-snug text-[var(--text-muted)]">
                Launch work, pick up the newest blocked run, and keep the recent pipeline health in
                view without leaving the overview.
              </p>
            </div>

            <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
              <ActionCard
                eyebrow="Primary action"
                title="Create a run"
                description="Start a new production run from the same operator surface used to inspect and triage existing work."
                tone="info"
                action={
                  <RunLaunchButton
                    label="Create Run"
                    defaultMode="production"
                    redirectResource={ResourceName.Runs}
                  />
                }
              />
              <ActionCard
                eyebrow="Attention"
                title="Inspect blocked run"
                description={attentionCopy.description}
                tone={attentionRun ? "warning" : "default"}
                action={
                  <Button
                    variant="secondary"
                    disabled={!attentionRun}
                    onClick={() => {
                      if (!attentionRun) return;
                      if (attentionRun.kind === "run") {
                        redirect("show", ResourceName.Runs, attentionRun.run_id);
                        return;
                      }
                      // No id to open — hand the operator the filtered queue
                      // instead of a dead disabled button (#670).
                      redirect(
                        `/${ResourceName.Runs}?filter=${encodeURIComponent(
                          JSON.stringify({ status: attentionRun.status }),
                        )}`,
                      );
                    }}
                  >
                    {attentionCopy.buttonLabel}
                  </Button>
                }
              />
              <ActionCard
                eyebrow="Queue"
                title="Open run queue"
                description="Switch to the list view when you want the full operator queue, then filter by state to clear the next item."
                tone="info"
                action={
                  <Button variant="secondary" onClick={() => redirect("list", ResourceName.Runs)}>
                    Open queue
                  </Button>
                }
              />
            </div>

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
              <StatCard label="Sources" value={stats.source_count} />
              <StatCard label="Total Runs" value={stats.total_runs} />
              <StatCard label="Total Artifacts" value={stats.total_artifacts} />
              <StatCard
                label="Success Rate"
                value={successRate}
                tone={successRateTone(successRate)}
              />
            </div>
          </div>
        </Panel>

        <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
          <Panel className="p-5">
            <div className="space-y-4">
              <div>
                <h2 className="text-xl font-bold leading-tight text-[var(--foreground)]">
                  Runs by status
                </h2>
                <p className="mt-1 text-sm text-[var(--text-muted)]">
                  Run lifecycle across <strong>all {stats.total_runs} runs</strong>. These are queue
                  states (pending / running / completed), not pipeline health.
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                {Object.entries(stats.run_by_status).map(([status, count]) => (
                  <Pill key={status} level={runRecordStatusToLevel(status)}>
                    {status}: {count}
                  </Pill>
                ))}
                {Object.keys(stats.run_by_status).length === 0 && (
                  <p className="text-sm text-[var(--text-muted)]">No runs yet.</p>
                )}
              </div>
            </div>
          </Panel>

          <Panel className="p-5">
            <div className="space-y-4">
              <div>
                <h2 className="text-xl font-bold leading-tight text-[var(--foreground)]">
                  Recent health snapshot
                </h2>
                <p className="mt-1 text-sm text-[var(--text-muted)]">
                  Pipeline health (acquisition → DI → projection) for{" "}
                  <strong>only the {recentHealth.length} most recent runs</strong> — a different
                  vocabulary and a different scope from the run lifecycle beside it. It says nothing
                  about older runs.
                </p>
              </div>
              {healthLoading ? (
                <Spinner label="Loading pipeline health..." />
              ) : healthError ? (
                <InlineAlert tone="warning">{healthError}</InlineAlert>
              ) : (
                <div className="flex flex-wrap gap-2">
                  <Pill level={pipelineHealthToLevel("ok")}>ok: {recentHealthSummary.ok}</Pill>
                  <Pill level={pipelineHealthToLevel("blocked")}>
                    blocked: {recentHealthSummary.blocked}
                  </Pill>
                  <Pill level={pipelineHealthToLevel("failed")}>
                    failed: {recentHealthSummary.failed}
                  </Pill>
                  <Pill level={pipelineHealthToLevel("in_progress")}>
                    in progress: {recentHealthSummary.in_progress}
                  </Pill>
                  <Pill level="neutral">unavailable: {recentHealthSummary.unavailable}</Pill>
                </div>
              )}
            </div>
          </Panel>
        </div>

        <SourceHealthCard />

        <Panel id="recent-run-health" className="p-5">
          <div className="space-y-4">
            <div>
              <h2 className="text-xl font-bold leading-tight text-[var(--foreground)]">
                Recent runs
              </h2>
              <p className="mt-1 text-sm text-[var(--text-muted)]">
                Newest runs stay in view here. Click a row to inspect the full run, or use the
                status chips above to prioritize the queue.
              </p>
            </div>

            <DataTable
              records={stats.recent_runs}
              columns={recentRunColumns}
              getRowId={(run) => run.run_id}
              onRowClick={(run) => redirect("show", ResourceName.Runs, run.run_id)}
              getRowLabel={(run) => `Open run ${run.run_id}`}
              empty="No runs found. Create a source and trigger a run to get started."
            />
          </div>
        </Panel>

        <div className="border-t border-[var(--border)] pt-6">
          <CorrectionMetricsCard />
        </div>
      </div>
    </div>
  );
}
