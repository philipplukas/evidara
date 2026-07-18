"use client";

import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Link,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
} from "@mui/material";
import type { ReactNode } from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { type Identifier, useGetList, useRecordContext } from "react-admin";
import { publicConfig } from "../../config/publicConfig";
import type {
  CapturedResourceRecord,
  DocumentLifecycleRecord,
  ProcessingStatusRecord,
  ProviderJobRecord,
  RawArtifactRecord,
  RunPipelineHealth,
  RunPipelineHealthStage,
  RunPreviewSummary,
  RunRecord,
} from "../../lib/admin/dataProvider";
import { controlPlaneActions } from "../../lib/admin/dataProvider";
import { emitOperatorJourneyEvent } from "../../lib/admin/operatorJourneyTelemetry";
import { formatSwissDateTime } from "../../lib/format/date";
import {
  type AdminStatusLevel,
  adminLevelBorder,
  pipelineHealthToLevel,
  StatusBadge,
} from "../shared/StatusBadge";
import {
  type ChecklistItem,
  type ChecklistState,
  deriveOperatorChecklist,
} from "./operatorChecklist";

const LIST_PARAMS = {
  pagination: { page: 1, perPage: 100 },
  sort: { field: "created_at", order: "DESC" as const },
};

const RUN_READINESS_CONFIRMED_KEY_PREFIX = "evidara_run_readiness_confirmed:";
const RUN_READINESS_BLOCKED_CODES_KEY_PREFIX = "evidara_run_readiness_blocked_codes:";
const RUN_VERIFICATION_OPENED_KEY_PREFIX = "evidara_run_verification_opened:";

type SectionColumn<TRecord extends { id: Identifier }> = {
  header: string;
  render: (record: TRecord) => ReactNode;
};

type RunTableSectionProps<TRecord extends { id: Identifier }> = {
  sectionId?: string;
  title: string;
  description: string;
  rows: TRecord[] | undefined;
  isPending: boolean;
  error: unknown;
  emptyMessage: string;
  columns: SectionColumn<TRecord>[];
  defaultExpanded?: boolean;
  /**
   * When both `expanded` and `onExpandedChange` are supplied the accordion is
   * controlled — this lets the jump links reveal a collapsed section before
   * scrolling to it. Sections without a jump target stay uncontrolled and use
   * `defaultExpanded`.
   */
  expanded?: boolean;
  onExpandedChange?: (expanded: boolean) => void;
};

const formatDateTime = (value: string | null | undefined): string =>
  formatSwissDateTime(value) || "—";

const formatJson = (value: unknown): string => JSON.stringify(value, null, 2);

const renderInlineValue = (value: string | number | null | undefined): ReactNode => value ?? "—";

const overallSeverityByStatus = (
  status: RunPipelineHealth["overall_status"],
): "success" | "warning" | "error" | "info" => {
  if (status === "ok") return "success";
  if (status === "blocked") return "warning";
  if (status === "failed") return "error";
  return "info";
};

export const overallSummaryByStatus = (status: RunPipelineHealth["overall_status"]): string => {
  if (status === "ok") return "Pipeline stages are healthy.";
  if (status === "blocked")
    return "One or more stages need remediation before the run can progress.";
  if (status === "failed") return "A downstream stage failed and needs operator attention.";
  return "At least one stage is still moving through the pipeline.";
};

const stageBorderColorByStatus = (status: DisplayStageStatus): string =>
  adminLevelBorder(pipelineHealthToLevel(status));

function checklistStateToLevel(state: ChecklistState): AdminStatusLevel {
  if (state === "ok") return "healthy";
  if (state === "blocked") return "degraded";
  if (state === "in_progress") return "info";
  return "neutral";
}

function rowStatusLevel(isFailed: boolean): AdminStatusLevel {
  return isFailed ? "critical" : "neutral";
}

const renderCodeBlock = (value: unknown): ReactNode => {
  const json = formatJson(value);
  return (
    <Box
      component="pre"
      sx={{
        mb: 0,
        mt: 1,
        p: 1.5,
        overflowX: "auto",
        borderRadius: 2,
        backgroundColor: "var(--brand-wash-6)",
        fontSize: 12,
        lineHeight: 1.4,
      }}
    >
      {json}
    </Box>
  );
};

export type PipelineDecisionSupport = {
  whyItMatters: string;
  whatIsBlocked: string;
  whatChangedRecently: string;
  whatHappensIfIgnored: string;
};

/**
 * Stage status *as rendered*. The API only knows the five lifecycle values; the
 * admin adds `not_applicable` for stages that can no longer run (see
 * `projectPipelineStages`).
 */
export type DisplayStageStatus = RunPipelineHealthStage["status"] | "not_applicable";

export type DisplayPipelineStage = Omit<RunPipelineHealthStage, "status"> & {
  status: DisplayStageStatus;
};

const TERMINAL_FAILURE_RUN_STATUSES: readonly string[] = ["failed", "cancelled"];

/**
 * A run that ended as `failed` / `cancelled` will never advance again, so the
 * stages it never reached are dead, not queued.
 */
export function isTerminalFailureRunStatus(status: RunPipelineHealth["run_status"]): boolean {
  return TERMINAL_FAILURE_RUN_STATUSES.includes(status);
}

const notApplicableDetail = (runStatus: RunPipelineHealth["run_status"]): string =>
  runStatus === "cancelled"
    ? "Not applicable — the run was cancelled before this stage could start."
    : "Not applicable — the run failed before this stage could start.";

/**
 * `projectPipelineStages` — render-time projection of the API stage list.
 *
 * On a run that terminally failed (or was cancelled), the API still reports the
 * downstream stages it never reached as `pending`, with copy like "Awaiting DI
 * processing signal before projection stage starts." That reads as "work is
 * still coming" and makes a dead run look like it needs watching. Those stages
 * are re-labelled `not_applicable` instead.
 *
 * Runs that are still progressing (pending / running / completed) are returned
 * untouched — `pending` is genuinely correct there, and a healthy completed run
 * legitimately reports every stage `ok`.
 */
export function projectPipelineStages(health: RunPipelineHealth): DisplayPipelineStage[] {
  if (!isTerminalFailureRunStatus(health.run_status)) {
    return health.stages;
  }
  return health.stages.map((stage) =>
    stage.status === "pending"
      ? { ...stage, status: "not_applicable", detail: notApplicableDetail(health.run_status) }
      : stage,
  );
}

/** A stage needs operator attention only when it is neither healthy nor dead. */
export function stageNeedsAction(status: DisplayStageStatus): boolean {
  return status !== "ok" && status !== "not_applicable";
}

const stageLabel = (stage: DisplayPipelineStage): string => stage.stage.replaceAll("_", " ");

const mostRecentStage = (stages: DisplayPipelineStage[]): DisplayPipelineStage | null =>
  stages.reduce<DisplayPipelineStage | null>((latest, stage) => {
    if (!stage.updated_at) {
      return latest;
    }
    if (!latest?.updated_at) {
      return stage;
    }
    return new Date(stage.updated_at).getTime() > new Date(latest.updated_at).getTime()
      ? stage
      : latest;
  }, null);

export function buildPipelineDecisionSupport(options: {
  run: RunRecord;
  health: RunPipelineHealth | null;
}): PipelineDecisionSupport {
  const { run, health } = options;

  const whyItMatters =
    run.mode === "production"
      ? "This production run determines whether the source version can safely flow into the live operator surface."
      : "This preview run is the gate before promotion, so the result tells operators whether the version is ready.";

  if (!health) {
    return {
      whyItMatters,
      whatIsBlocked: "Pipeline health has not loaded yet, so the blocked state is still unknown.",
      whatChangedRecently:
        "The latest stage movement will appear once the pipeline health snapshot loads.",
      whatHappensIfIgnored:
        "Without an operator check, the run will remain in its current state and no remediation guidance will surface.",
    };
  }

  const stages = projectPipelineStages(health);
  const blockedStages = stages.filter(
    (stage) => stage.status === "blocked" || stage.status === "failed",
  );
  const skippedStages = stages.filter((stage) => stage.status === "not_applicable");
  const latestStage = mostRecentStage(stages);

  const blockedSummary =
    health.overall_status === "ok"
      ? "No stage is blocked right now."
      : blockedStages.length > 0
        ? `Blocked stages: ${blockedStages.map(stageLabel).join(", ")}.`
        : "No stage is blocked, but the pipeline is still moving and may need operator attention soon.";

  const whatIsBlocked =
    skippedStages.length > 0
      ? `${blockedSummary} Downstream stages that will never run: ${skippedStages.map(stageLabel).join(", ")}.`
      : blockedSummary;

  const whatChangedRecently = latestStage
    ? `Most recent stage update: ${stageLabel(latestStage)} is ${latestStage.status.replaceAll("_", " ")}.`
    : `Health snapshot recorded ${health.processing_status_event_count} processing events and ${health.document_lifecycle_event_count} lifecycle events.`;

  const whatHappensIfIgnored = isTerminalFailureRunStatus(health.run_status)
    ? `The run already ended as ${health.run_status}; the stages it never reached will not start on their own, so remediate and relaunch to make progress.`
    : health.overall_status === "ok"
      ? "Nothing urgent happens; the run remains a completed audit trail unless someone investigates it later."
      : health.overall_status === "blocked"
        ? "The run stays blocked until the relevant stage is remediated."
        : health.overall_status === "failed"
          ? "The failure remains unresolved and downstream progress will not clear itself."
          : "The pipeline continues to advance and may still require intervention if a later stage stops.";

  return {
    whyItMatters,
    whatIsBlocked,
    whatChangedRecently,
    whatHappensIfIgnored,
  };
}

function DecisionSupportItem({ label, value }: { label: string; value: string }) {
  return (
    <Paper variant="outlined" sx={{ p: 1.5, background: "var(--brand-wash-3)" }}>
      <Stack spacing={0.5}>
        <Typography variant="overline" color="text.secondary" sx={{ lineHeight: 1.2 }}>
          {label}
        </Typography>
        <Typography variant="body2" color="text.secondary">
          {value}
        </Typography>
      </Stack>
    </Paper>
  );
}

function PreviewSummarySection({ run }: { run: RunRecord }) {
  const [summary, setSummary] = useState<RunPreviewSummary | null>(null);
  const [isPending, setIsPending] = useState(run.mode === "preview");
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    if (run.mode !== "preview") {
      setSummary(null);
      setError(null);
      setIsPending(false);
      return;
    }

    let cancelled = false;
    setIsPending(true);
    setError(null);

    void controlPlaneActions
      .getRunPreviewSummary(run.run_id)
      .then((response) => {
        if (!cancelled) {
          setSummary(response);
        }
      })
      .catch((reason) => {
        if (!cancelled) {
          setError(reason);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setIsPending(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [run.mode, run.run_id]);

  if (run.mode !== "preview") {
    return null;
  }

  return (
    <Paper sx={{ p: 3 }}>
      <Stack spacing={2}>
        <Box>
          <Typography variant="h6">Preview Summary</Typography>
          <Typography variant="body2" color="text.secondary">
            Review heuristic signals before promoting this source version into production.
          </Typography>
        </Box>

        {isPending ? (
          <Stack direction="row" spacing={1.5} alignItems="center">
            <CircularProgress size={18} />
            <Typography variant="body2" color="text.secondary">
              Loading preview summary...
            </Typography>
          </Stack>
        ) : null}

        {!isPending && error ? (
          <Alert severity="error">
            {error instanceof Error ? error.message : "Unable to load preview summary."}
          </Alert>
        ) : null}

        {!isPending && !error && summary ? (
          <Stack spacing={2}>
            <Stack direction={{ xs: "column", md: "row" }} spacing={1.5} flexWrap="wrap">
              <Chip label={`URLs ${summary.captured_url_count}`} />
              <Chip label={`Artifacts ${summary.artifacts_count}`} />
              <Chip label={`Captured ${summary.captured_resources_count}`} />
              <Chip label={`PDFs ${summary.pdf_count}`} />
              <Chip label={`Decision pages ${summary.likely_decision_page_count}`} />
              <Chip label={`Boilerplate ${summary.likely_boilerplate_page_count}`} />
              <Chip label={`Duplicates ${summary.likely_duplicate_page_count}`} />
            </Stack>

            <Box>
              <Typography variant="subtitle2">Drift Checks</Typography>
              <Stack
                direction={{ xs: "column", md: "row" }}
                spacing={1.5}
                flexWrap="wrap"
                sx={{ pt: 1 }}
              >
                {summary.drift_checks.map((check) => (
                  <Chip
                    key={check.name}
                    label={`${check.name}: ${check.detail}`}
                    color={check.status === "warn" ? "warning" : "default"}
                    variant="outlined"
                  />
                ))}
              </Stack>
            </Box>

            <RunTableSection
              title="Content Type Breakdown"
              description="Observed content types for captured resources."
              rows={summary.content_type_breakdown.map((entry, index) => ({
                id: `${entry.content_type}-${index}`,
                ...entry,
              }))}
              isPending={false}
              error={null}
              emptyMessage="No content types were observed."
              columns={[
                { header: "Content type", render: (entry) => entry.content_type },
                { header: "Count", render: (entry) => entry.count },
              ]}
            />

            <RunTableSection
              title="Likely Decision Pages"
              description="Pages heuristically identified as candidate decisions."
              rows={summary.likely_decision_pages.map((page) => ({
                id: page.captured_resource_id,
                ...page,
              }))}
              isPending={false}
              error={null}
              emptyMessage="No likely decision pages were identified."
              columns={[
                { header: "Title", render: (page) => page.title ?? "Untitled" },
                {
                  header: "URL",
                  render: (page) => (
                    <Link href={page.final_url} target="_blank" rel="noreferrer">
                      {page.final_url}
                    </Link>
                  ),
                },
                { header: "Type", render: (page) => page.content_type },
                { header: "Reason", render: (page) => page.reason },
              ]}
            />

            <RunTableSection
              title="Likely Boilerplate Pages"
              description="Pages heuristically identified as boilerplate."
              rows={summary.likely_boilerplate_pages.map((page) => ({
                id: page.captured_resource_id,
                ...page,
              }))}
              isPending={false}
              error={null}
              emptyMessage="No likely boilerplate pages were identified."
              columns={[
                { header: "Title", render: (page) => page.title ?? "Untitled" },
                {
                  header: "URL",
                  render: (page) => (
                    <Link href={page.final_url} target="_blank" rel="noreferrer">
                      {page.final_url}
                    </Link>
                  ),
                },
                { header: "Type", render: (page) => page.content_type },
                { header: "Reason", render: (page) => page.reason },
              ]}
            />

            <RunTableSection
              title="Likely Duplicate Pages"
              description="Pages that look duplicated based on checksum matching."
              rows={summary.likely_duplicate_pages.map((page) => ({
                id: page.captured_resource_id,
                ...page,
              }))}
              isPending={false}
              error={null}
              emptyMessage="No likely duplicate pages were identified."
              columns={[
                { header: "Title", render: (page) => page.title ?? "Untitled" },
                {
                  header: "URL",
                  render: (page) => (
                    <Link href={page.final_url} target="_blank" rel="noreferrer">
                      {page.final_url}
                    </Link>
                  ),
                },
                { header: "Type", render: (page) => page.content_type },
                { header: "Reason", render: (page) => page.reason },
              ]}
            />
          </Stack>
        ) : null}
      </Stack>
    </Paper>
  );
}

function RunSectionNav({ onJump }: { onJump: (href: string) => void }) {
  return (
    <Paper variant="outlined" sx={{ p: 2 }}>
      <Stack spacing={1.5}>
        <Box>
          <Typography variant="h6">Lifecycle sections</Typography>
          <Typography variant="body2" color="text.secondary">
            Jump straight to the stage that needs attention.
          </Typography>
        </Box>
        <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
          <Button onClick={() => onJump("#provider-jobs-section")} variant="outlined" size="small">
            Provider jobs
          </Button>
          <Button
            onClick={() => onJump("#di-processing-status-section")}
            variant="outlined"
            size="small"
          >
            DI processing
          </Button>
          <Button
            onClick={() => onJump("#document-lifecycle-section")}
            variant="outlined"
            size="small"
          >
            Document lifecycle
          </Button>
        </Stack>
      </Stack>
    </Paper>
  );
}

export function stageNextAction(stage: DisplayPipelineStage): string {
  if (stage.status === "ok") return "No action required.";
  if (stage.status === "not_applicable") {
    return "No action — this stage will not run for this run.";
  }
  if (stage.stage === "acquisition") {
    return "Check provider jobs for dispatch/crawl status and retry or cancel when stuck.";
  }
  if (stage.stage === "document_intelligence") {
    return "Inspect DI processing status events and error summaries for remediation.";
  }
  if (stage.stage === "projection") {
    return "Confirm document lifecycle events are being emitted for this run.";
  }
  return "Verify lifecycle search disposition and confirm indexed document visibility in legal-search.";
}

export function stageActionTarget(
  stage: DisplayPipelineStage,
  options: { legalSearchUrl?: string; evidenceRunbookPath: string },
): { label: string; href: string } {
  if (stage.stage === "acquisition") {
    return { label: "Jump to provider jobs", href: "#provider-jobs-section" };
  }
  if (stage.stage === "document_intelligence") {
    return { label: "Jump to DI processing", href: "#di-processing-status-section" };
  }
  if (stage.stage === "projection") {
    return { label: "Jump to document lifecycle", href: "#document-lifecycle-section" };
  }
  if (options.legalSearchUrl) {
    return { label: "Open legal-search verification", href: options.legalSearchUrl };
  }
  return { label: "Open evidence runbook", href: options.evidenceRunbookPath };
}

/**
 * `sectionIdFromAnchor` — strip the leading `#` from an in-page anchor href so
 * it can be resolved with `document.getElementById`. Callers pass the raw
 * `stageActionTarget` href (e.g. `#di-processing-status-section`).
 */
export function sectionIdFromAnchor(href: string): string {
  return href.startsWith("#") ? href.slice(1) : href;
}

/**
 * `scrollToInPageSection` — smooth-scroll to the element behind an in-page
 * anchor **without** letting the click reach react-admin's HashRouter.
 *
 * These detail pages render under a `HashRouter`, so a plain `<a href="#foo">`
 * click mutates `location.hash` to `#foo`, which the router parses as a route
 * change and bounces the operator to the "Not Found" page (issue: jump links
 * left the run detail entirely). Resolving the target element and calling
 * `scrollIntoView` ourselves keeps navigation entirely client-side and never
 * touches the hash. No-ops safely if the element is not in the DOM.
 */
export function scrollToInPageSection(href: string): void {
  if (typeof document === "undefined") {
    return;
  }
  const target = document.getElementById(sectionIdFromAnchor(href));
  target?.scrollIntoView({ behavior: "smooth", block: "start" });
}

function PipelineHealthSection({
  run,
  onJump,
}: {
  run: RunRecord;
  onJump: (href: string) => void;
}) {
  const [health, setHealth] = useState<RunPipelineHealth | null>(null);
  const [isPending, setIsPending] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [readinessConfirmed, setReadinessConfirmed] = useState(false);
  const [readinessBlockedCodes, setReadinessBlockedCodes] = useState<string[]>([]);
  const [verificationOpened, setVerificationOpened] = useState(false);
  // Use the "or undefined" form: this section hides the verification button
  // entirely when no legal-search URL is configured rather than defaulting
  // to localhost (matches pre-refactor behavior).
  const legalSearchUrl = publicConfig.legalSearchBaseUrlOrUndefined;
  const evidenceRunbookPath =
    "https://github.com/philipplukas/evidara/blob/main/docs/runbooks/interaction-flow-validation.md";
  const healthLoadStartedAtRef = useRef<number | null>(null);
  const firstRemediationEventEmittedRef = useRef(false);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    const readiness = window.localStorage.getItem(
      `${RUN_READINESS_CONFIRMED_KEY_PREFIX}${run.run_id}`,
    );
    const blockedRaw = window.localStorage.getItem(
      `${RUN_READINESS_BLOCKED_CODES_KEY_PREFIX}${run.run_id}`,
    );
    const verification = window.localStorage.getItem(
      `${RUN_VERIFICATION_OPENED_KEY_PREFIX}${run.run_id}`,
    );
    setReadinessConfirmed(readiness === "true");
    setVerificationOpened(verification === "true");
    if (blockedRaw) {
      try {
        const parsed = JSON.parse(blockedRaw);
        setReadinessBlockedCodes(Array.isArray(parsed) ? parsed.map(String) : []);
      } catch {
        setReadinessBlockedCodes([]);
      }
    } else {
      setReadinessBlockedCodes([]);
    }
  }, [run.run_id]);

  const checklistItems = useMemo<ChecklistItem[]>(
    () =>
      deriveOperatorChecklist({
        run,
        health,
        readinessConfirmed,
        readinessBlockedCodes,
        verificationOpened,
      }),
    [run, health, readinessConfirmed, readinessBlockedCodes, verificationOpened],
  );

  const displayStages = useMemo(() => (health ? projectPipelineStages(health) : null), [health]);
  const stageSummary = useMemo(
    () =>
      displayStages?.reduce(
        (counts, stage) => {
          counts[stage.status] = (counts[stage.status] ?? 0) + 1;
          return counts;
        },
        {
          ok: 0,
          blocked: 0,
          failed: 0,
          in_progress: 0,
          pending: 0,
          not_applicable: 0,
        } as Record<string, number>,
      ) ?? null,
    [displayStages],
  );
  const decisionSupport = useMemo(
    () => buildPipelineDecisionSupport({ run, health }),
    [health, run],
  );

  useEffect(() => {
    let cancelled = false;
    setIsPending(true);
    setError(null);
    healthLoadStartedAtRef.current = Date.now();
    firstRemediationEventEmittedRef.current = false;

    void controlPlaneActions
      .getRunPipelineHealth(run.run_id)
      .then((response) => {
        if (!cancelled) {
          setHealth(response);
          emitOperatorJourneyEvent("pipeline_health_loaded", {
            run_id: run.run_id,
            source_id: run.source_id,
            source_version_id: run.source_version_id,
            mode: run.mode,
            duration_ms:
              healthLoadStartedAtRef.current != null
                ? Date.now() - healthLoadStartedAtRef.current
                : undefined,
          });
        }
      })
      .catch((reason) => {
        if (!cancelled) {
          setError(reason);
          setHealth(null);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setIsPending(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [run.mode, run.run_id, run.source_id, run.source_version_id]);

  return (
    <Paper sx={{ p: 3 }}>
      <Stack spacing={2}>
        <Box>
          <Typography variant="h6">Pipeline Health</Typography>
          <Typography variant="body2" color="text.secondary">
            Use the anchors below to jump from overview into the stage that needs attention.
          </Typography>
        </Box>

        {isPending ? (
          <Stack direction="row" spacing={1.5} alignItems="center">
            <CircularProgress size={18} />
            <Typography variant="body2" color="text.secondary">
              Loading pipeline health...
            </Typography>
          </Stack>
        ) : null}

        {!isPending && error ? (
          <Alert severity="error">
            {error instanceof Error ? error.message : "Unable to load pipeline health."}
          </Alert>
        ) : null}

        {!isPending && !error && health ? (
          <Stack spacing={2}>
            <Alert
              severity={overallSeverityByStatus(health.overall_status)}
              icon={false}
              sx={{ alignItems: "flex-start" }}
            >
              <Stack spacing={1}>
                <Typography variant="body2" sx={{ fontWeight: 600 }}>
                  {overallSummaryByStatus(health.overall_status)}
                </Typography>
                <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" alignItems="center">
                  <StatusBadge
                    level={pipelineHealthToLevel(health.overall_status)}
                    label={`Overall ${health.overall_status}`}
                  />
                  <Chip size="small" label={`Run ${health.run_status}`} variant="outlined" />
                  <Typography variant="caption" color="text.secondary">
                    {health.processing_status_event_count} processing
                    {" / "}
                    {health.document_lifecycle_event_count} lifecycle events
                  </Typography>
                </Stack>
              </Stack>
            </Alert>

            <Paper variant="outlined" sx={{ p: 1.5, background: "var(--brand-wash-3)" }}>
              <Stack spacing={1.25}>
                <Box>
                  <Typography variant="subtitle2">Decision support</Typography>
                  <Typography variant="body2" color="text.secondary">
                    The cues below translate the health snapshot into operator decisions.
                  </Typography>
                </Box>
                <Box
                  sx={{
                    display: "grid",
                    gap: 1,
                    gridTemplateColumns: { xs: "1fr", md: "repeat(2, minmax(0, 1fr))" },
                  }}
                >
                  <DecisionSupportItem
                    label="Why this matters"
                    value={decisionSupport.whyItMatters}
                  />
                  <DecisionSupportItem
                    label="What is blocked"
                    value={decisionSupport.whatIsBlocked}
                  />
                  <DecisionSupportItem
                    label="What changed recently"
                    value={decisionSupport.whatChangedRecently}
                  />
                  <DecisionSupportItem
                    label="If you do nothing"
                    value={decisionSupport.whatHappensIfIgnored}
                  />
                </Box>
              </Stack>
            </Paper>

            {stageSummary ? (
              <Paper variant="outlined" sx={{ p: 1.5 }}>
                <Stack spacing={1}>
                  <Typography variant="subtitle2">Stage summary</Typography>
                  <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
                    <StatusBadge level="healthy" label={`Healthy ${stageSummary.ok ?? 0}`} />
                    <StatusBadge
                      level="degraded"
                      label={`Needs action ${(stageSummary.blocked ?? 0) + (stageSummary.failed ?? 0)}`}
                    />
                    <StatusBadge
                      level="info"
                      label={`In progress ${stageSummary.in_progress ?? 0}`}
                    />
                    <StatusBadge
                      level="neutral"
                      label={`Pending ${stageSummary.pending ?? 0}`}
                      emphasis="subtle"
                    />
                    {(stageSummary.not_applicable ?? 0) > 0 ? (
                      <StatusBadge
                        level="neutral"
                        label={`Not applicable ${stageSummary.not_applicable}`}
                        emphasis="subtle"
                      />
                    ) : null}
                  </Stack>
                </Stack>
              </Paper>
            ) : null}

            <Paper variant="outlined" sx={{ p: 1.5 }}>
              <Stack spacing={1}>
                <Typography variant="subtitle2">Operator Checklist</Typography>
                {checklistItems.map((item) => (
                  <Stack
                    key={item.key}
                    direction={{ xs: "column", md: "row" }}
                    spacing={1}
                    alignItems="start"
                  >
                    <StatusBadge
                      level={checklistStateToLevel(item.state)}
                      label={item.state.replaceAll("_", " ")}
                    />
                    <Box>
                      <Typography variant="body2">{item.label}</Typography>
                      <Typography variant="caption" color="text.secondary">
                        {item.detail}
                      </Typography>
                    </Box>
                  </Stack>
                ))}
                {!verificationOpened && legalSearchUrl ? (
                  <Button
                    component="a"
                    href={legalSearchUrl}
                    target="_blank"
                    rel="noreferrer"
                    variant="outlined"
                    size="small"
                    onClick={() => {
                      if (typeof window !== "undefined") {
                        window.localStorage.setItem(
                          `${RUN_VERIFICATION_OPENED_KEY_PREFIX}${run.run_id}`,
                          "true",
                        );
                      }
                      setVerificationOpened(true);
                      emitOperatorJourneyEvent("legal_search_verification_opened", {
                        run_id: run.run_id,
                        source_id: run.source_id,
                        source_version_id: run.source_version_id,
                        mode: run.mode,
                        action_label: "Operator checklist legal-search verification",
                        action_href: legalSearchUrl,
                      });
                    }}
                  >
                    Open legal-search verification
                  </Button>
                ) : null}
              </Stack>
            </Paper>

            <Stack spacing={1.5}>
              {(displayStages ?? health.stages).map((stage) => {
                const actionTarget = stageActionTarget(stage, {
                  legalSearchUrl,
                  evidenceRunbookPath,
                });
                const isInPageAnchor = actionTarget.href.startsWith("#");
                const isHealthy = stage.status === "ok";
                const isNotApplicable = stage.status === "not_applicable";
                const needsAction = stageNeedsAction(stage.status);
                const emitRemediationClick = () => {
                  if (!firstRemediationEventEmittedRef.current) {
                    emitOperatorJourneyEvent("remediation_action_clicked", {
                      run_id: run.run_id,
                      source_id: run.source_id,
                      source_version_id: run.source_version_id,
                      mode: run.mode,
                      stage: stage.stage,
                      action_label: actionTarget.label,
                      action_href: actionTarget.href,
                    });
                    firstRemediationEventEmittedRef.current = true;
                  }
                };
                return (
                  <Paper
                    key={stage.stage}
                    variant="outlined"
                    sx={{
                      p: 1.5,
                      borderLeftWidth: 4,
                      borderLeftStyle: "solid",
                      borderLeftColor: stageBorderColorByStatus(stage.status),
                    }}
                  >
                    <Stack spacing={1}>
                      <Stack
                        direction="row"
                        spacing={1}
                        alignItems="flex-start"
                        justifyContent="space-between"
                        useFlexGap
                        flexWrap="wrap"
                      >
                        <Box sx={{ minWidth: 0 }}>
                          <Typography variant="subtitle2" sx={{ textTransform: "capitalize" }}>
                            {stage.stage.replaceAll("_", " ")}
                          </Typography>
                          <Typography variant="caption" color="text.secondary">
                            {formatDateTime(stage.updated_at)}
                          </Typography>
                        </Box>
                        <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
                          <StatusBadge
                            level={pipelineHealthToLevel(stage.status)}
                            label={stage.status.replaceAll("_", " ")}
                          />
                          <StatusBadge
                            level={needsAction ? "degraded" : isHealthy ? "healthy" : "neutral"}
                            label={
                              needsAction
                                ? "Action required"
                                : isHealthy
                                  ? "No action required"
                                  : "Will not run"
                            }
                            {...(isNotApplicable ? { emphasis: "subtle" as const } : {})}
                          />
                        </Stack>
                      </Stack>
                      <Typography variant="body2" color="text.secondary">
                        {stage.detail}
                      </Typography>
                      {!needsAction ? (
                        <Typography
                          variant="caption"
                          color={isHealthy ? "success.main" : "text.secondary"}
                        >
                          {isHealthy
                            ? "No remediation required."
                            : "No remediation possible — this stage will not run for this run."}
                        </Typography>
                      ) : (
                        <Paper
                          variant="outlined"
                          sx={{
                            p: 1.25,
                            background:
                              stage.status === "failed"
                                ? "rgba(211, 47, 47, 0.04)"
                                : "rgba(245, 158, 11, 0.06)",
                          }}
                        >
                          <Stack
                            direction={{ xs: "column", md: "row" }}
                            spacing={1.25}
                            alignItems={{ xs: "stretch", md: "center" }}
                            justifyContent="space-between"
                          >
                            <Box sx={{ minWidth: 0 }}>
                              <Typography variant="body2" sx={{ fontWeight: 600 }}>
                                Next action: {stageNextAction(stage)}
                              </Typography>
                              <Typography variant="caption" color="text.secondary">
                                The button on the right opens the most relevant remediation surface.
                              </Typography>
                            </Box>
                            {isInPageAnchor ? (
                              // In-page jumps must NOT be `<a href="#...">`:
                              // under the HashRouter that rewrites the route
                              // and drops the operator on the Not Found page.
                              // Scroll (and reveal) the target section instead.
                              <Button
                                size="small"
                                variant="contained"
                                onClick={() => {
                                  emitRemediationClick();
                                  onJump(actionTarget.href);
                                }}
                              >
                                {actionTarget.label}
                              </Button>
                            ) : (
                              <Button
                                component="a"
                                href={actionTarget.href}
                                target="_blank"
                                rel="noreferrer"
                                size="small"
                                variant="contained"
                                onClick={emitRemediationClick}
                              >
                                {actionTarget.label}
                              </Button>
                            )}
                          </Stack>
                        </Paper>
                      )}
                    </Stack>
                  </Paper>
                );
              })}
            </Stack>

            <Stack direction={{ xs: "column", md: "row" }} spacing={1}>
              {legalSearchUrl ? (
                <Button
                  component="a"
                  href={legalSearchUrl}
                  target="_blank"
                  rel="noreferrer"
                  variant="outlined"
                  size="small"
                  onClick={() => {
                    if (typeof window !== "undefined") {
                      window.localStorage.setItem(
                        `${RUN_VERIFICATION_OPENED_KEY_PREFIX}${run.run_id}`,
                        "true",
                      );
                    }
                    setVerificationOpened(true);
                    emitOperatorJourneyEvent("legal_search_verification_opened", {
                      run_id: run.run_id,
                      source_id: run.source_id,
                      source_version_id: run.source_version_id,
                      mode: run.mode,
                      action_label: "Pipeline section legal-search verification",
                      action_href: legalSearchUrl,
                    });
                  }}
                >
                  Open legal-search verification
                </Button>
              ) : null}
              <Button
                component="a"
                href={evidenceRunbookPath}
                target="_blank"
                rel="noreferrer"
                variant="text"
                size="small"
              >
                Open related evidence runbook
              </Button>
            </Stack>
          </Stack>
        ) : null}
      </Stack>
    </Paper>
  );
}

function RunTableSection<TRecord extends { id: Identifier }>({
  sectionId,
  title,
  description,
  rows,
  isPending,
  error,
  emptyMessage,
  columns,
  defaultExpanded = false,
  expanded,
  onExpandedChange,
}: RunTableSectionProps<TRecord>) {
  const rowCount = rows?.length ?? 0;
  const summaryChip = !isPending && !error && (
    <Chip label={`${rowCount} ${rowCount === 1 ? "row" : "rows"}`} size="small" sx={{ ml: 1 }} />
  );

  const controlProps =
    expanded !== undefined && onExpandedChange !== undefined
      ? { expanded, onChange: (_event: unknown, isOpen: boolean) => onExpandedChange(isOpen) }
      : { defaultExpanded };

  return (
    <Accordion
      id={sectionId}
      {...controlProps}
      disableGutters
      sx={{ "&::before": { display: "none" } }}
    >
      <AccordionSummary expandIcon={<ExpandMoreIcon />}>
        <Box sx={{ display: "flex", alignItems: "center" }}>
          <Typography variant="h6">{title}</Typography>
          {summaryChip}
        </Box>
      </AccordionSummary>
      <AccordionDetails>
        <Stack spacing={2}>
          <Typography variant="body2" color="text.secondary">
            {description}
          </Typography>

          {isPending ? (
            <Stack direction="row" spacing={1.5} alignItems="center">
              <CircularProgress size={18} />
              <Typography variant="body2" color="text.secondary">
                Loading {title.toLowerCase()} rows...
              </Typography>
            </Stack>
          ) : null}

          {!isPending && error ? (
            <Alert severity="error">
              {error instanceof Error ? error.message : `Unable to load ${title.toLowerCase()}.`}
            </Alert>
          ) : null}

          {!isPending && !error && rows?.length === 0 ? (
            <Typography variant="body2" color="text.secondary">
              {emptyMessage}
            </Typography>
          ) : null}

          {!isPending && !error && rows && rows.length > 0 ? (
            <Box sx={{ overflowX: "auto" }}>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    {columns.map((column) => (
                      <TableCell key={column.header}>{column.header}</TableCell>
                    ))}
                  </TableRow>
                </TableHead>
                <TableBody>
                  {rows.map((row) => (
                    <TableRow key={row.id}>
                      {columns.map((column) => (
                        <TableCell key={column.header}>{column.render(row)}</TableCell>
                      ))}
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </Box>
          ) : null}
        </Stack>
      </AccordionDetails>
    </Accordion>
  );
}

export function RunDetailSections() {
  const run = useRecordContext<RunRecord>();

  const capturedResources = useGetList<CapturedResourceRecord>(
    "run-captured-resources",
    {
      ...LIST_PARAMS,
      filter: { run_id: run?.run_id },
    },
    { enabled: Boolean(run?.run_id) },
  );
  const rawArtifacts = useGetList<RawArtifactRecord>(
    "run-raw-artifacts",
    {
      ...LIST_PARAMS,
      filter: { run_id: run?.run_id },
    },
    { enabled: Boolean(run?.run_id) },
  );
  const providerJobs = useGetList<ProviderJobRecord>(
    "run-provider-jobs",
    {
      ...LIST_PARAMS,
      filter: { run_id: run?.run_id },
    },
    { enabled: Boolean(run?.run_id) },
  );
  const processingStatus = useGetList<ProcessingStatusRecord>(
    "run-processing-status",
    {
      ...LIST_PARAMS,
      filter: { run_id: run?.run_id },
    },
    { enabled: Boolean(run?.run_id) },
  );
  const documentLifecycle = useGetList<DocumentLifecycleRecord>(
    "run-document-lifecycle",
    {
      ...LIST_PARAMS,
      filter: { run_id: run?.run_id },
    },
    { enabled: Boolean(run?.run_id) },
  );

  // Tracks which jump-target accordions the operator has revealed. The jump
  // links open the section here (so a collapsed target is visible) and then
  // scroll to it — see `scrollToInPageSection` for why we never use the hash.
  const [revealedSections, setRevealedSections] = useState<Record<string, boolean>>({});

  const handleJump = useCallback((href: string) => {
    setRevealedSections((prev) => ({ ...prev, [sectionIdFromAnchor(href)]: true }));
    scrollToInPageSection(href);
  }, []);

  const sectionControls = (sectionId: string) => ({
    expanded: revealedSections[sectionId] ?? false,
    onExpandedChange: (isOpen: boolean) =>
      setRevealedSections((prev) => ({ ...prev, [sectionId]: isOpen })),
  });

  if (!run) {
    return null;
  }

  return (
    <Stack spacing={3} sx={{ pt: 2 }}>
      <RunSectionNav onJump={handleJump} />
      <PipelineHealthSection run={run} onJump={handleJump} />
      <PreviewSummarySection run={run} />

      <RunTableSection
        sectionId="provider-jobs-section"
        {...sectionControls("provider-jobs-section")}
        title="Provider Jobs"
        description="Provider-level crawl job state and webhook progression for this run."
        rows={providerJobs.data}
        isPending={providerJobs.isPending}
        error={providerJobs.error}
        emptyMessage="No provider jobs were recorded for this run."
        columns={[
          { header: "Provider", render: (job) => job.provider },
          { header: "External job", render: (job) => renderInlineValue(job.external_job_id) },
          {
            header: "Status",
            render: (job) => (
              <StatusBadge level={rowStatusLevel(job.status === "failed")} label={job.status} />
            ),
          },
          { header: "Last event", render: (job) => renderInlineValue(job.last_event_type) },
          { header: "Updated", render: (job) => formatDateTime(job.updated_at) },
          {
            header: "Payloads",
            render: (job) => (
              <Box>
                <Typography variant="caption" sx={{ fontWeight: 600 }}>
                  Request
                </Typography>
                {renderCodeBlock(job.request_payload)}
                <Typography variant="caption" sx={{ fontWeight: 600 }}>
                  Response
                </Typography>
                {renderCodeBlock(job.response_payload)}
              </Box>
            ),
          },
        ]}
      />

      <RunTableSection
        title="Captured Resources"
        description="Pages and files captured from the source during this run."
        rows={capturedResources.data}
        isPending={capturedResources.isPending}
        error={capturedResources.error}
        emptyMessage="No captured resources were recorded for this run."
        columns={[
          {
            header: "Resource",
            render: (resource) => (
              <Box>
                <Typography variant="body2" sx={{ fontWeight: 600 }}>
                  {resource.title ?? "Untitled resource"}
                </Typography>
                <Link href={resource.final_url} target="_blank" rel="noreferrer">
                  {resource.final_url}
                </Link>
              </Box>
            ),
          },
          { header: "Type", render: (resource) => resource.content_type },
          { header: "HTTP", render: (resource) => renderInlineValue(resource.http_status) },
          { header: "Depth", render: (resource) => renderInlineValue(resource.discovery_depth) },
          { header: "Checksum", render: (resource) => renderInlineValue(resource.checksum) },
          { header: "Fetched", render: (resource) => formatDateTime(resource.fetched_at) },
        ]}
      />

      <RunTableSection
        title="Raw Artifacts"
        description="Stored raw artifacts published by the acquisition provider for this run."
        rows={rawArtifacts.data}
        isPending={rawArtifacts.isPending}
        error={rawArtifacts.error}
        emptyMessage="No raw artifacts were recorded for this run."
        columns={[
          { header: "Artifact", render: (artifact) => artifact.artifact_id },
          { header: "Type", render: (artifact) => artifact.content_type },
          { header: "Storage path", render: (artifact) => artifact.storage_path },
          { header: "Created", render: (artifact) => formatDateTime(artifact.created_at) },
          {
            header: "Metadata",
            render: (artifact) => renderCodeBlock(artifact.artifact_metadata),
          },
        ]}
      />

      <RunTableSection
        sectionId="di-processing-status-section"
        {...sectionControls("di-processing-status-section")}
        title="DI Processing Status"
        description="Document-intelligence processing updates correlated to this run."
        rows={processingStatus.data}
        isPending={processingStatus.isPending}
        error={processingStatus.error}
        emptyMessage="No DI processing status updates have been received for this run."
        columns={[
          {
            header: "Status",
            render: (update) => (
              <StatusBadge
                level={rowStatusLevel(update.status === "failed")}
                label={update.status}
              />
            ),
          },
          {
            header: "Document",
            render: (update) =>
              update.document_id
                ? `${update.document_id} rev ${update.document_revision ?? "—"}`
                : "—",
          },
          { header: "Manifest", render: (update) => update.processing_manifest_id },
          { header: "Occurred", render: (update) => formatDateTime(update.occurred_at) },
          { header: "Error", render: (update) => renderInlineValue(update.error_summary) },
        ]}
      />

      <RunTableSection
        sectionId="document-lifecycle-section"
        {...sectionControls("document-lifecycle-section")}
        title="Document Lifecycle"
        description="Published or withdrawn document lifecycle events emitted by document-intelligence."
        rows={documentLifecycle.data}
        isPending={documentLifecycle.isPending}
        error={documentLifecycle.error}
        emptyMessage="No document lifecycle events have been received for this run."
        columns={[
          { header: "Event", render: (event) => event.event_type },
          {
            header: "Document",
            render: (event) => `${event.document_id} rev ${event.document_revision}`,
          },
          { header: "Lifecycle", render: (event) => renderInlineValue(event.lifecycle_status) },
          { header: "Reason", render: (event) => renderInlineValue(event.reason_code) },
          { header: "Occurred", render: (event) => formatDateTime(event.occurred_at) },
        ]}
      />
    </Stack>
  );
}
