"use client";

import { Box, Button, Chip, Divider, Paper, Stack, Typography } from "@mui/material";
import { useMemo } from "react";
import {
  Datagrid,
  DateField,
  FunctionField,
  List,
  NumberField,
  SelectInput,
  TextField,
  useListContext,
  useRedirect,
} from "react-admin";
import type { RunRecord } from "../../lib/admin/dataProvider";
import { CancelRunButton } from "./RunActions";
import { RunLaunchButton } from "./RunLaunchDialog";

const STATUS_TONES: Record<string, "success" | "error" | "warning" | "info" | "default"> = {
  completed: "success",
  failed: "error",
  running: "info",
  pending: "warning",
  cancelled: "default",
};

const runFilters = [
  <SelectInput
    key="mode"
    source="mode"
    label="Run mode"
    alwaysOn
    choices={[
      { id: "preview", name: "Preview" },
      { id: "production", name: "Production" },
    ]}
  />,
  <SelectInput
    key="status"
    source="status"
    label="Run status"
    alwaysOn
    choices={[
      { id: "pending", name: "Pending" },
      { id: "running", name: "Running" },
      { id: "completed", name: "Completed" },
      { id: "failed", name: "Failed" },
      { id: "cancelled", name: "Cancelled" },
    ]}
  />,
];

function RunQueueHeader() {
  const { data, total, isLoading, filterValues, setFilters } = useListContext<RunRecord>();
  const redirect = useRedirect();

  const runs = useMemo(() => Object.values(data ?? {}), [data]);
  const activeFilterSummary = useMemo(() => {
    const segments = [
      filterValues.mode ? `mode: ${String(filterValues.mode)}` : null,
      filterValues.status ? `status: ${String(filterValues.status)}` : null,
    ].filter((segment): segment is string => segment !== null);

    return segments.join(" · ");
  }, [filterValues.mode, filterValues.status]);
  const hasActiveFilters = activeFilterSummary.length > 0;

  const attentionRun = useMemo(
    () =>
      runs.find((run) => ["failed", "pending", "running"].includes(run.status)) ?? runs[0] ?? null,
    [runs],
  );

  const statusCounts = useMemo(
    () =>
      runs.reduce(
        (counts, run) => {
          counts[run.status] += 1;
          return counts;
        },
        {
          pending: 0,
          running: 0,
          completed: 0,
          failed: 0,
          cancelled: 0,
        },
      ),
    [runs],
  );

  const focusStatus = (status: RunRecord["status"]) => {
    setFilters({ ...filterValues, status }, undefined, false);
  };

  const clearFilters = () => {
    setFilters({}, undefined, false);
  };

  return (
    <Stack spacing={2.5} sx={{ mb: 2.5 }}>
      <Paper
        sx={{
          p: { xs: 2.25, md: 3 },
          background:
            "linear-gradient(145deg, rgba(15, 76, 129, 0.06), rgba(154, 122, 74, 0.05) 60%, rgba(255, 253, 248, 0.92))",
        }}
      >
        <Stack spacing={2}>
          <Stack direction={{ xs: "column", lg: "row" }} spacing={2} alignItems="stretch">
            <Stack spacing={0.9} sx={{ flex: 1, minWidth: 0 }}>
              <Typography
                variant="overline"
                sx={{
                  letterSpacing: "0.18em",
                  color: "text.secondary",
                  lineHeight: 1.15,
                }}
              >
                Run queue
              </Typography>
              <Typography variant="h5" sx={{ fontWeight: 700, lineHeight: 1.12 }}>
                Task-led run operations
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ maxWidth: 760 }}>
                Start a new run, jump to the newest attention item, or filter the queue down to the
                exact state you want to clear next.
              </Typography>
            </Stack>

            <Stack
              direction={{ xs: "column", sm: "row" }}
              spacing={1.25}
              sx={{ alignSelf: "center" }}
            >
              <RunLaunchButton
                label="Create Run"
                defaultMode="production"
                redirectResource="runs"
              />
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
                {attentionRun ? "Inspect attention run" : "No attention run"}
              </Button>
              {hasActiveFilters ? (
                <Button variant="text" onClick={clearFilters}>
                  Clear filters
                </Button>
              ) : null}
            </Stack>
          </Stack>

          <Divider />

          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
            <Chip
              label={hasActiveFilters ? `Filtering ${activeFilterSummary}` : "All queue states"}
              variant="outlined"
            />
            <Chip
              label={`Pending ${statusCounts.pending}`}
              color="warning"
              variant={filterValues.status === "pending" ? "filled" : "outlined"}
              onClick={() => focusStatus("pending")}
            />
            <Chip
              label={`Running ${statusCounts.running}`}
              color="info"
              variant={filterValues.status === "running" ? "filled" : "outlined"}
              onClick={() => focusStatus("running")}
            />
            <Chip
              label={`Failed ${statusCounts.failed}`}
              color="error"
              variant={filterValues.status === "failed" ? "filled" : "outlined"}
              onClick={() => focusStatus("failed")}
            />
            <Chip
              label={`Completed ${statusCounts.completed}`}
              color="success"
              variant={filterValues.status === "completed" ? "filled" : "outlined"}
              onClick={() => focusStatus("completed")}
            />
            <Chip
              label={`Cancelled ${statusCounts.cancelled}`}
              variant={filterValues.status === "cancelled" ? "filled" : "outlined"}
              onClick={() => focusStatus("cancelled")}
            />
            <Chip
              label={`Showing ${runs.length} of ${total ?? runs.length} runs`}
              variant="outlined"
            />
            {isLoading ? <Chip label="Loading queue..." variant="outlined" /> : null}
          </Stack>
        </Stack>
      </Paper>

      <Paper sx={{ p: 2.5 }}>
        <Stack spacing={1.25}>
          <Stack direction={{ xs: "column", sm: "row" }} spacing={1} justifyContent="space-between">
            <Box>
              <Typography variant="h6">Current queue</Typography>
              <Typography variant="body2" color="text.secondary">
                Click a row to inspect the full run. The state column uses operator language so the
                next step is obvious at a glance.
              </Typography>
            </Box>
            {attentionRun ? (
              <Button
                variant="outlined"
                color="warning"
                onClick={() => {
                  redirect("show", "runs", attentionRun.run_id);
                }}
                sx={{ alignSelf: { xs: "flex-start", sm: "center" } }}
              >
                Open attention run
              </Button>
            ) : null}
          </Stack>
          <Typography variant="body2" color="text.secondary">
            Filtered views help narrow the queue to the next operator step.
          </Typography>
        </Stack>
      </Paper>
    </Stack>
  );
}

function RunStateField() {
  return (
    <FunctionField<RunRecord>
      label="State"
      render={(record) => (
        <Stack spacing={0.5}>
          <Chip
            size="small"
            label={record.status}
            color={STATUS_TONES[record.status] ?? "default"}
          />
          <Typography variant="caption" color="text.secondary">
            {record.status === "pending"
              ? "Queued for the next operator pass."
              : record.status === "running"
                ? "Work is active now."
                : record.status === "failed"
                  ? (record.failure_reason ?? "Needs operator review.")
                  : record.status === "completed"
                    ? "Work finished successfully."
                    : "Stopped by an operator."}
          </Typography>
        </Stack>
      )}
    />
  );
}

function RunListGrid() {
  return (
    <Datagrid rowClick="show" bulkActionButtons={false}>
      <FunctionField<RunRecord>
        source="run_id"
        label="Run"
        render={(record) => (
          <Stack spacing={0.35}>
            <Typography variant="body2" sx={{ fontFamily: "monospace" }}>
              {record.run_id}
            </Typography>
            <Typography variant="caption" color="text.secondary">
              {record.mode}
            </Typography>
          </Stack>
        )}
      />
      <TextField source="source_name" label="Source" />
      <TextField source="version_label" label="Version" />
      <RunStateField />
      <NumberField source="captured_resources_count" label="Captured" />
      <NumberField source="artifacts_count" label="Artifacts" />
      <DateField source="created_at" label="Created" showTime />
      <DateField source="updated_at" label="Updated" showTime />
      <CancelRunButton />
    </Datagrid>
  );
}

export function RunList() {
  return (
    <List
      resource="runs"
      title="Runs"
      perPage={25}
      sort={{ field: "created_at", order: "DESC" }}
      filters={runFilters}
      actions={false}
    >
      <RunQueueHeader />
      <RunListGrid />
    </List>
  );
}
