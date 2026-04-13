"use client";

import { Alert, Box, Chip, Paper, Stack, Typography } from "@mui/material";
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

  return (
    <Paper variant="outlined" sx={{ p: 2, mb: 2 }}>
      <Stack spacing={1.5}>
        <Box
          sx={{
            display: "flex",
            flexDirection: { xs: "column", md: "row" },
            justifyContent: "space-between",
            gap: 2,
          }}
        >
          <Box>
            <Typography variant="overline" color="text.secondary">
              Run overview
            </Typography>
            <Typography variant="h6">Run {run.run_id}</Typography>
            <Typography variant="body2" color="text.secondary">
              {run.source_id} · {run.source_version_id} · {run.mode}
            </Typography>
          </Box>
          <RunActionStack />
        </Box>

        <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
          <Chip size="small" color={statusChipColor(run.status)} label={run.status} />
          <Chip size="small" color={modeChipColor(run.mode)} label={run.mode} />
          <Chip
            size="small"
            variant="outlined"
            label={`Captured ${run.captured_resources_count}`}
          />
          <Chip size="small" variant="outlined" label={`Artifacts ${run.artifacts_count}`} />
          <Chip size="small" variant="outlined" label={`Duration ${formatDuration(run)}`} />
        </Stack>

        <Typography variant="body2" color="text.secondary">
          The lifecycle sections below are ordered so the next operator action is never far from the
          overview.
        </Typography>

        {run.failure_reason ? (
          <Alert severity={run.status === "failed" ? "error" : "warning"} icon={false}>
            <Typography variant="body2" sx={{ fontWeight: 600 }}>
              Failure reason
            </Typography>
            <Typography variant="body2" color="text.secondary">
              {run.failure_reason}
            </Typography>
          </Alert>
        ) : null}
      </Stack>
    </Paper>
  );
}

export function RunShow() {
  return (
    <Show resource="runs" title="Run Detail">
      <SimpleShowLayout>
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
