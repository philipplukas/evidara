"use client";

import { Alert, Box, Chip, Paper, Stack, Typography } from "@mui/material";
import { useEffect, useState } from "react";
import {
  DateField,
  FunctionField,
  NumberField,
  Show,
  SimpleShowLayout,
  TextField,
  useRecordContext,
} from "react-admin";
import type { RunRecord } from "../../lib/admin/dataProvider";
import {
  describeLegalSearchHandoff,
  type LegalSearchHandoff,
  resolveLegalSearchHandoff,
} from "../../lib/admin/navigationContext";
import { RunActionStack } from "./RunActions";
import { RunDetailSections } from "./RunDetailSections";

const statusChipColor = (
  status: RunRecord["status"],
): "default" | "info" | "success" | "warning" | "error" => {
  if (status === "completed") return "success";
  if (status === "running") return "info";
  if (status === "failed") return "error";
  if (status === "cancelled") return "warning";
  return "default";
};

const modeChipColor = (mode: RunRecord["mode"]): "info" | "success" =>
  mode === "production" ? "success" : "info";

export type RunDecisionSupport = {
  whyItMatters: string;
  whatIsBlocked: string;
  whatChangedRecently: string;
  whatHappensIfIgnored: string;
};

export type RunHandoffGuidance = {
  whyYouAreHere: string;
  whatToCheckNext: string;
};

const describeRunNextStep = (run: RunRecord): string => {
  if (run.status === "failed") {
    return "Open the pipeline sections below and use the failure reason to pinpoint the blocked stage.";
  }
  if (run.status === "running") {
    return "The run is active. Watch the pipeline health and stage sections for the next operator cue.";
  }
  if (run.status === "pending") {
    return "The run is queued. Review readiness and wait for the first stage update.";
  }
  if (run.status === "completed") {
    return "The run completed successfully. Use the lifecycle sections as the audit trail.";
  }
  return "The run was cancelled. Review the detail sections if the stop was unexpected.";
};

export function buildRunDecisionSupport(run: RunRecord): RunDecisionSupport {
  const whyItMatters =
    run.mode === "production"
      ? "This production run reflects the live path for the source version and should be treated as operator-critical."
      : "This preview run is the checkpoint before promotion, so its outcome decides whether the version is ready.";

  const whatIsBlocked =
    run.status === "failed"
      ? run.failure_reason
        ? `The run is blocked by a recorded failure: ${run.failure_reason}`
        : "The run failed and is blocked until the failing stage is remediated."
      : run.status === "running"
        ? "No stage is blocked yet, but the active pipeline may stop if an upstream stage fails."
        : run.status === "pending"
          ? "Nothing is blocked yet because the run has not started."
          : run.status === "cancelled"
            ? "The run was stopped, so there is no remaining blocked stage to clear."
            : "No blocker is visible from the run record.";

  const whatChangedRecently =
    run.status === "completed"
      ? `The run finalized ${run.captured_resources_count} captured resources and ${run.artifacts_count} artifacts.`
      : run.status === "running"
        ? "The pipeline is still changing, so the stage sections below are the best source of the latest movement."
        : run.status === "pending"
          ? "The run is still waiting in queue, so no stage work has started yet."
          : run.status === "failed"
            ? "The latest recorded change is the failure outcome that operators need to inspect."
            : "No new stage activity is expected after cancellation.";

  const whatHappensIfIgnored =
    run.status === "pending"
      ? "It stays queued until the platform starts it or an operator cancels it."
      : run.status === "running"
        ? "It keeps progressing and may complete or fail without intervention."
        : run.status === "failed"
          ? "It remains failed and the blocked stage will not clear on its own."
          : run.status === "completed"
            ? "It stays as a stable audit trail unless the outcome needs review."
            : "No further pipeline work will happen for this run.";

  return {
    whyItMatters,
    whatIsBlocked,
    whatChangedRecently,
    whatHappensIfIgnored,
  };
}

function readLegalSearchHandoff(): LegalSearchHandoff | null {
  if (typeof window === "undefined") {
    return null;
  }

  return resolveLegalSearchHandoff(
    new URLSearchParams(window.location.search),
    window.location.href,
  );
}

export function buildRunHandoffGuidance(
  run: RunRecord,
  handoff: LegalSearchHandoff,
): RunHandoffGuidance | null {
  if (!handoff.hasOrigin) {
    return null;
  }

  const contextSummary = describeLegalSearchHandoff(handoff);
  const whyYouAreHere = `You came from legal search. ${contextSummary}.`;
  const whatToCheckNext = `${describeRunNextStep(run)} ${
    handoff.selectedId
      ? `Use the selected item (${handoff.selectedId}) to confirm the source/version pair above is the one you expected.`
      : "Use the source and version IDs above to confirm the run matches the result you were investigating."
  }`;

  return {
    whyYouAreHere,
    whatToCheckNext,
  };
}

function DecisionSupportItem({ label, value }: { label: string; value: string }) {
  return (
    <Paper variant="outlined" sx={{ p: 1.5, background: "rgba(15, 76, 129, 0.03)" }}>
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

function formatDuration(record: RunRecord): string {
  if (!record.started_at || !record.completed_at) {
    return "—";
  }

  const ms = new Date(record.completed_at).getTime() - new Date(record.started_at).getTime();
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  return `${Math.floor(ms / 60000)}m ${Math.round((ms % 60000) / 1000)}s`;
}

function RunDurationField() {
  const record = useRecordContext<RunRecord>();
  if (!record) {
    return <Typography variant="body2">-</Typography>;
  }
  if (!record.started_at || !record.completed_at) return <Typography variant="body2">-</Typography>;
  return <Typography variant="body2">{formatDuration(record)}</Typography>;
}

function RunOverviewCard() {
  const run = useRecordContext<RunRecord>();

  if (!run) {
    return null;
  }

  const decisionSupport = buildRunDecisionSupport(run);

  return (
    <Paper
      variant="outlined"
      sx={{
        p: 2,
        mb: 2,
        background: "linear-gradient(180deg, rgba(15, 76, 129, 0.04), rgba(255, 255, 255, 0.98))",
      }}
    >
      <Stack spacing={2}>
        <Stack
          direction={{ xs: "column", md: "row" }}
          spacing={2}
          justifyContent="space-between"
          alignItems="stretch"
        >
          <Stack spacing={1} sx={{ flex: 1, minWidth: 0 }}>
            <Typography variant="overline" color="text.secondary">
              Run overview
            </Typography>
            <Typography variant="h6" sx={{ fontWeight: 700 }}>
              Run {run.run_id}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              {run.source_id} · {run.source_version_id}
            </Typography>
            <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
              <Chip size="small" color={statusChipColor(run.status)} label={run.status} />
              <Chip size="small" color={modeChipColor(run.mode)} label={run.mode} />
              <Chip
                size="small"
                variant="outlined"
                label={`Source version ${run.source_version_id}`}
              />
            </Stack>
          </Stack>
          <Box sx={{ alignSelf: { xs: "stretch", md: "flex-start" } }}>
            <RunActionStack />
          </Box>
        </Stack>

        <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
          <Chip
            size="small"
            variant="outlined"
            label={`Captured ${run.captured_resources_count}`}
          />
          <Chip size="small" variant="outlined" label={`Artifacts ${run.artifacts_count}`} />
          <Chip size="small" variant="outlined" label={`Duration ${formatDuration(run)}`} />
        </Stack>

        <Typography variant="body2" color="text.secondary">
          {describeRunNextStep(run)}
        </Typography>

        <Paper variant="outlined" sx={{ p: 1.5, background: "rgba(15, 76, 129, 0.03)" }}>
          <Stack spacing={1.25}>
            <Box>
              <Typography variant="subtitle2">Decision support</Typography>
              <Typography variant="body2" color="text.secondary">
                The four cues below answer the operator questions we use most often on active runs.
              </Typography>
            </Box>
            <Box
              sx={{
                display: "grid",
                gap: 1,
                gridTemplateColumns: { xs: "1fr", md: "repeat(2, minmax(0, 1fr))" },
              }}
            >
              <DecisionSupportItem label="Why this matters" value={decisionSupport.whyItMatters} />
              <DecisionSupportItem label="What is blocked" value={decisionSupport.whatIsBlocked} />
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

        {run.failure_reason ? (
          <Alert severity={run.status === "failed" ? "error" : "warning"} icon={false}>
            <Stack spacing={0.5}>
              <Typography variant="body2" sx={{ fontWeight: 600 }}>
                Failure reason
              </Typography>
              <Typography variant="body2" color="text.secondary">
                {run.failure_reason}
              </Typography>
            </Stack>
          </Alert>
        ) : null}
      </Stack>
    </Paper>
  );
}

function RunHandoffCard() {
  const run = useRecordContext<RunRecord>();
  const [handoff, setHandoff] = useState<LegalSearchHandoff | null>(null);

  useEffect(() => {
    setHandoff(readLegalSearchHandoff());
  }, []);

  if (!run || !handoff) {
    return null;
  }

  const guidance = buildRunHandoffGuidance(run, handoff);

  if (!guidance) {
    return null;
  }

  return (
    <Paper
      variant="outlined"
      sx={{
        p: 2,
        mb: 2,
        background: "linear-gradient(180deg, rgba(15, 76, 129, 0.035), rgba(255, 255, 255, 0.97))",
      }}
    >
      <Stack spacing={1.5}>
        <Box>
          <Typography variant="subtitle2">Legal search handoff</Typography>
          <Typography variant="body2" color="text.secondary">
            Why you are here and what to check next before acting on this run.
          </Typography>
        </Box>

        <Typography variant="body2" color="text.secondary">
          {guidance.whyYouAreHere}
        </Typography>

        <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
          {handoff.query ? <Chip size="small" variant="outlined" label={handoff.query} /> : null}
          {handoff.scopeLabel ? (
            <Chip size="small" variant="outlined" label={handoff.scopeLabel} />
          ) : null}
          {handoff.selectedId ? (
            <Chip size="small" variant="outlined" label={`Selected item: ${handoff.selectedId}`} />
          ) : null}
        </Stack>

        <Typography variant="body2" color="text.secondary">
          {guidance.whatToCheckNext}
        </Typography>
      </Stack>
    </Paper>
  );
}

export function RunShow() {
  return (
    <Show resource="runs" title="Run Detail">
      <SimpleShowLayout>
        <RunHandoffCard />
        <RunOverviewCard />
        <TextField source="run_id" label="Run" />
        <TextField source="source_id" label="Source ID" />
        <TextField source="source_version_id" label="Source version ID" />
        <TextField source="mode" label="Mode" />
        <TextField source="status" label="Status" />
        <NumberField source="captured_resources_count" label="Captured resources" />
        <NumberField source="artifacts_count" label="Artifacts" />
        <TextField source="failure_reason" label="Failure reason" emptyText="-" />
        <DateField source="started_at" label="Started" showTime emptyText="-" />
        <DateField source="completed_at" label="Completed" showTime emptyText="-" />
        <FunctionField label="Duration" render={() => <RunDurationField />} />
        <DateField source="created_at" label="Created" showTime />
        <DateField source="updated_at" label="Updated" showTime />
        <RunDetailSections />
      </SimpleShowLayout>
    </Show>
  );
}
