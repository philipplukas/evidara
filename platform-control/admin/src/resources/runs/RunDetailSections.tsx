"use client";

import {
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
import { useEffect, useMemo, useRef, useState } from "react";
import { type Identifier, useGetList, useRecordContext } from "react-admin";
import type {
  CapturedResourceRecord,
  DocumentLifecycleRecord,
  ProcessingStatusRecord,
  ProviderJobRecord,
  RawArtifactRecord,
  RunPipelineHealth,
  RunPreviewSummary,
  RunRecord,
} from "../../lib/admin/dataProvider";
import { controlPlaneActions } from "../../lib/admin/dataProvider";
import { emitOperatorJourneyEvent } from "../../lib/admin/operatorJourneyTelemetry";
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
};

const formatDateTime = (value: string | null | undefined): string =>
  value
    ? new Intl.DateTimeFormat("en", {
        dateStyle: "medium",
        timeStyle: "short",
      }).format(new Date(value))
    : "—";

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

const stageBorderColorByStatus = (
  status: RunPipelineHealth["stages"][number]["status"],
): string => {
  if (status === "failed") return "error.main";
  if (status === "blocked") return "warning.main";
  if (status === "in_progress") return "info.main";
  if (status === "ok") return "success.main";
  return "divider";
};

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
        backgroundColor: "rgba(15, 76, 129, 0.06)",
        fontSize: 12,
        lineHeight: 1.4,
      }}
    >
      {json}
    </Box>
  );
};

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

function RunSectionNav() {
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
          <Button component="a" href="#provider-jobs-section" variant="outlined" size="small">
            Provider jobs
          </Button>
          <Button
            component="a"
            href="#di-processing-status-section"
            variant="outlined"
            size="small"
          >
            DI processing
          </Button>
          <Button component="a" href="#document-lifecycle-section" variant="outlined" size="small">
            Document lifecycle
          </Button>
        </Stack>
      </Stack>
    </Paper>
  );
}

function pipelineChipColor(status: string): "default" | "info" | "warning" | "error" | "success" {
  if (status === "ok") return "success";
  if (status === "failed") return "error";
  if (status === "blocked") return "warning";
  if (status === "in_progress") return "info";
  return "default";
}

export function stageNextAction(stage: RunPipelineHealth["stages"][number]): string {
  if (stage.status === "ok") return "No action required.";
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
  stage: RunPipelineHealth["stages"][number],
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

function checklistChipColor(state: ChecklistState): "default" | "info" | "warning" | "success" {
  if (state === "ok") return "success";
  if (state === "blocked") return "warning";
  if (state === "in_progress") return "info";
  return "default";
}

function PipelineHealthSection({ run }: { run: RunRecord }) {
  const [health, setHealth] = useState<RunPipelineHealth | null>(null);
  const [isPending, setIsPending] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [readinessConfirmed, setReadinessConfirmed] = useState(false);
  const [readinessBlockedCodes, setReadinessBlockedCodes] = useState<string[]>([]);
  const [verificationOpened, setVerificationOpened] = useState(false);
  const legalSearchUrl = process.env.NEXT_PUBLIC_LEGAL_SEARCH_URL?.trim();
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
                <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
                  <Chip
                    size="small"
                    label={`Overall ${health.overall_status}`}
                    color={pipelineChipColor(health.overall_status)}
                    variant="outlined"
                  />
                  <Chip size="small" label={`Run ${health.run_status}`} variant="outlined" />
                  <Chip
                    size="small"
                    label={`Processing events ${health.processing_status_event_count}`}
                  />
                  <Chip
                    size="small"
                    label={`Lifecycle events ${health.document_lifecycle_event_count}`}
                  />
                </Stack>
              </Stack>
            </Alert>

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
                    <Chip size="small" label={item.state} color={checklistChipColor(item.state)} />
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
              {health.stages.map((stage) => {
                const actionTarget = stageActionTarget(stage, {
                  legalSearchUrl,
                  evidenceRunbookPath,
                });
                const isInPageAnchor = actionTarget.href.startsWith("#");
                const isHealthy = stage.status === "ok";
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
                        alignItems="center"
                        useFlexGap
                        flexWrap="wrap"
                      >
                        <Typography variant="subtitle2" sx={{ textTransform: "capitalize" }}>
                          {stage.stage.replace("_", " ")}
                        </Typography>
                        <Chip
                          size="small"
                          label={stage.status}
                          color={pipelineChipColor(stage.status)}
                          variant="outlined"
                        />
                      </Stack>
                      <Typography variant="body2" color="text.secondary">
                        {stage.detail}
                      </Typography>
                      {isHealthy ? (
                        <Typography variant="caption" color="success.main">
                          No remediation required.
                        </Typography>
                      ) : (
                        <Alert
                          severity={stage.status === "failed" ? "error" : "warning"}
                          icon={false}
                        >
                          <Stack
                            direction={{ xs: "column", md: "row" }}
                            spacing={1}
                            alignItems="center"
                            justifyContent="space-between"
                          >
                            <Typography variant="body2" sx={{ fontWeight: 600 }}>
                              Next action: {stageNextAction(stage)}
                            </Typography>
                            <Button
                              component="a"
                              href={actionTarget.href}
                              target={isInPageAnchor ? undefined : "_blank"}
                              rel={isInPageAnchor ? undefined : "noreferrer"}
                              size="small"
                              variant="contained"
                              onClick={() => {
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
                              }}
                            >
                              {actionTarget.label}
                            </Button>
                          </Stack>
                        </Alert>
                      )}
                      <Typography variant="caption" color="text.secondary">
                        Updated: {formatDateTime(stage.updated_at)}
                      </Typography>
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
}: RunTableSectionProps<TRecord>) {
  return (
    <Paper id={sectionId} sx={{ p: 3 }}>
      <Stack spacing={2}>
        <Box>
          <Typography variant="h6">{title}</Typography>
          <Typography variant="body2" color="text.secondary">
            {description}
          </Typography>
        </Box>

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
    </Paper>
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

  if (!run) {
    return null;
  }

  return (
    <Stack spacing={3} sx={{ pt: 2 }}>
      <RunSectionNav />
      <PipelineHealthSection run={run} />
      <PreviewSummarySection run={run} />

      <RunTableSection
        sectionId="provider-jobs-section"
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
              <Chip
                size="small"
                label={job.status}
                color={job.status === "failed" ? "error" : "default"}
              />
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
              <Chip
                size="small"
                label={update.status}
                color={update.status === "failed" ? "error" : "default"}
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
