"use client";

import { Box, Button, Chip, Divider, Paper, Stack, Typography } from "@mui/material";
import { useEffect, useMemo, useRef } from "react";
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

type RunQueueFilterValues = Partial<Pick<RunRecord, "mode" | "status">>;

const STATUS_TONES: Record<string, "success" | "error" | "warning" | "info" | "default"> = {
  completed: "success",
  failed: "error",
  running: "info",
  pending: "warning",
  cancelled: "default",
};

const ACTIONABLE_STATUSES: RunRecord["status"][] = ["failed", "running", "pending"];

const RUN_QUEUE_PRESETS = [
  {
    key: "all",
    label: "All queue states",
    description: "Show the full queue with no status or mode filter.",
  },
  {
    key: "attention",
    label: "Attention first",
    description: "Jump to the most urgent actionable run in the inbox.",
  },
  {
    key: "pending",
    label: "Pending",
    description: "Review queued work before it starts moving.",
  },
  {
    key: "running",
    label: "Running",
    description: "Watch active runs and their current progress.",
  },
  {
    key: "failed",
    label: "Failed",
    description: "Focus on blocked work that needs remediation.",
  },
  {
    key: "production",
    label: "Production",
    description: "Limit the queue to production-mode runs.",
  },
  {
    key: "preview",
    label: "Preview",
    description: "Limit the queue to preview-mode runs.",
  },
] as const;

export const describeRunState = (record: RunRecord): string => {
  if (record.status === "pending") {
    return "Queued. Review readiness or open the run when it becomes active.";
  }
  if (record.status === "running") {
    return "Active now. Watch the pipeline sections for the next operator cue.";
  }
  if (record.status === "failed") {
    return "Blocked. Review the failure reason in the detail page.";
  }
  if (record.status === "completed") {
    return "Finished successfully. Use the detail view for audit evidence.";
  }
  return "Stopped by an operator. Review the detail page if this was unexpected.";
};

export const summarizeRunFilters = (filterValues: RunQueueFilterValues): string => {
  const segments = [
    filterValues.mode ? `mode: ${String(filterValues.mode)}` : null,
    filterValues.status ? `status: ${String(filterValues.status)}` : null,
  ].filter((segment): segment is string => segment !== null);

  return segments.join(" · ");
};

export const selectAttentionRun = (runs: RunRecord[]): RunRecord | null => {
  for (const status of ACTIONABLE_STATUSES) {
    const candidate = runs.find((run) => run.status === status);
    if (candidate) {
      return candidate;
    }
  }

  return runs[0] ?? null;
};

export const isKeyboardShortcutInputTarget = (target: EventTarget | null): boolean => {
  if (!target || typeof target !== "object") {
    return false;
  }

  const element = target as {
    tagName?: string;
    isContentEditable?: boolean;
    contentEditable?: string;
    closest?: (selector: string) => unknown;
  };

  const tagName = element.tagName?.toUpperCase();

  return (
    tagName === "INPUT" ||
    tagName === "TEXTAREA" ||
    tagName === "SELECT" ||
    element.isContentEditable === true ||
    element.contentEditable === "true" ||
    (typeof element.closest === "function" && element.closest("[contenteditable='true']") !== null)
  );
};

export type RunQueueKeyboardShortcutAction =
  | { type: "focus-attention" }
  | { type: "open-attention"; runId: string };

export const getRunQueueKeyboardShortcutAction = (
  event: Pick<KeyboardEvent, "altKey" | "ctrlKey" | "defaultPrevented" | "key" | "metaKey">,
  target: EventTarget | null,
  attentionRun: RunRecord | null,
): RunQueueKeyboardShortcutAction | null => {
  if (
    event.defaultPrevented ||
    event.metaKey ||
    event.ctrlKey ||
    event.altKey ||
    isKeyboardShortcutInputTarget(target)
  ) {
    return null;
  }

  if (event.key === "/") {
    return { type: "focus-attention" };
  }

  if ((event.key === "o" || event.key === "O") && attentionRun) {
    return { type: "open-attention", runId: attentionRun.run_id };
  }

  return null;
};

type SetRunFilters = (
  filters: RunQueueFilterValues,
  displayedFilters?: unknown,
  debounce?: boolean,
) => void;

const focusStatus = (
  setFilters: SetRunFilters,
  filterValues: RunQueueFilterValues,
  status: RunRecord["status"],
) => {
  setFilters({ ...filterValues, status }, undefined, false);
};

const focusMode = (
  setFilters: SetRunFilters,
  filterValues: RunQueueFilterValues,
  mode: RunRecord["mode"],
) => {
  setFilters({ ...filterValues, mode }, undefined, false);
};

const focusAttention = (
  setFilters: SetRunFilters,
  filterValues: RunQueueFilterValues,
  runs: RunRecord[],
) => {
  const attentionRun = selectAttentionRun(runs);
  const status = attentionRun?.status ?? "pending";
  setFilters({ ...filterValues, status }, undefined, false);
};

const clearFilters = (setFilters: SetRunFilters) => {
  setFilters({}, undefined, false);
};

const getPresetDescription = (presetKey: string, attentionRun: RunRecord | null) => {
  if (presetKey === "attention") {
    return attentionRun
      ? `Attention first: ${attentionRun.source_name} (${attentionRun.status}).`
      : "Attention first: nothing actionable is waiting.";
  }

  const preset = RUN_QUEUE_PRESETS.find((item) => item.key === presetKey);
  return preset?.description ?? "Show the full queue with no status or mode filter.";
};

function RunQueueHeader() {
  const { data, total, isLoading, filterValues, setFilters } = useListContext<RunRecord>();
  const redirect = useRedirect();
  const attentionButtonRef = useRef<HTMLButtonElement | null>(null);

  const runs = useMemo(() => Object.values(data ?? {}), [data]);
  const activeFilterSummary = useMemo(() => summarizeRunFilters(filterValues), [filterValues]);
  const hasActiveFilters = activeFilterSummary.length > 0;
  const attentionRun = useMemo(() => selectAttentionRun(runs), [runs]);
  const attentionStatus = attentionRun?.status ?? null;

  const actionableRunCount = useMemo(
    () => runs.filter((run) => ACTIONABLE_STATUSES.includes(run.status)).length,
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

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const shortcut = getRunQueueKeyboardShortcutAction(event, event.target, attentionRun);
      if (!shortcut) {
        return;
      }

      event.preventDefault();

      if (shortcut.type === "focus-attention") {
        attentionButtonRef.current?.focus();
        return;
      }

      redirect("show", "runs", shortcut.runId);
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [attentionRun, redirect]);

  const presetButtonSx = (isActive: boolean) => ({
    borderRadius: 999,
    justifyContent: "flex-start",
    textTransform: "none",
    fontWeight: 600,
    borderColor: isActive ? "rgba(15, 76, 129, 0.5)" : "rgba(29, 41, 61, 0.18)",
    backgroundColor: isActive ? "rgba(15, 76, 129, 0.08)" : "transparent",
    "&:hover": {
      backgroundColor: isActive ? "rgba(15, 76, 129, 0.12)" : "rgba(15, 76, 129, 0.04)",
    },
  });

  return (
    <Stack spacing={2.5} sx={{ mb: 2.5 }}>
      <Paper
        sx={{
          p: { xs: 2.25, md: 3 },
          background:
            "linear-gradient(145deg, rgba(15, 76, 129, 0.06), rgba(154, 122, 74, 0.05) 60%, rgba(255, 253, 248, 0.92))",
        }}
      >
        <Stack spacing={2.5}>
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
              <Typography variant="caption" color="text.secondary">
                Press / to focus the attention preset. Press O to open the attention run.
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
                <Button variant="text" onClick={() => clearFilters(setFilters)}>
                  Clear filters
                </Button>
              ) : null}
            </Stack>
          </Stack>

          <Divider />

          <Stack spacing={1.25}>
            <Stack direction="row" spacing={1} alignItems="center" justifyContent="space-between">
              <Typography
                variant="subtitle2"
                sx={{ letterSpacing: "0.08em", textTransform: "uppercase" }}
              >
                Quick presets
              </Typography>
              <Typography variant="caption" color="text.secondary">
                Inbox shortcuts for triage
              </Typography>
            </Stack>

            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
              {RUN_QUEUE_PRESETS.map((preset) => {
                if (preset.key === "all") {
                  const isActive = !hasActiveFilters;
                  return (
                    <Button
                      key={preset.key}
                      variant={isActive ? "contained" : "outlined"}
                      size="small"
                      onClick={() => clearFilters(setFilters)}
                      sx={presetButtonSx(isActive)}
                    >
                      {preset.label}
                    </Button>
                  );
                }

                if (preset.key === "attention") {
                  const isActive = attentionStatus === filterValues.status;
                  return (
                    <Button
                      key={preset.key}
                      ref={attentionButtonRef}
                      variant={isActive ? "contained" : "outlined"}
                      color="warning"
                      size="small"
                      onClick={() => focusAttention(setFilters, filterValues, runs)}
                      sx={presetButtonSx(isActive)}
                    >
                      {preset.label}
                    </Button>
                  );
                }

                if (preset.key === "production" || preset.key === "preview") {
                  const mode = preset.key === "production" ? "production" : "preview";
                  const isActive = filterValues.mode === mode;
                  return (
                    <Button
                      key={preset.key}
                      variant={isActive ? "contained" : "outlined"}
                      size="small"
                      onClick={() => focusMode(setFilters, filterValues, mode)}
                      sx={presetButtonSx(isActive)}
                    >
                      {preset.label}
                    </Button>
                  );
                }

                const isActive = filterValues.status === preset.key;
                const status = preset.key as RunRecord["status"];
                return (
                  <Button
                    key={preset.key}
                    variant={isActive ? "contained" : "outlined"}
                    color={
                      status === "failed" ? "error" : status === "running" ? "info" : "warning"
                    }
                    size="small"
                    onClick={() => focusStatus(setFilters, filterValues, status)}
                    sx={presetButtonSx(isActive)}
                  >
                    {preset.label}
                  </Button>
                );
              })}
            </Stack>

            <Typography variant="caption" color="text.secondary">
              {getPresetDescription(
                filterValues.status === "failed" ||
                  filterValues.status === "running" ||
                  filterValues.status === "pending"
                  ? filterValues.status
                  : "attention",
                attentionRun,
              )}
            </Typography>
          </Stack>

          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
            <Chip
              label={hasActiveFilters ? `Filtering ${activeFilterSummary}` : "All queue states"}
              variant="outlined"
            />
            <Chip
              label={`Pending ${statusCounts.pending}`}
              color="warning"
              variant={filterValues.status === "pending" ? "filled" : "outlined"}
              onClick={() => focusStatus(setFilters, filterValues, "pending")}
            />
            <Chip
              label={`Running ${statusCounts.running}`}
              color="info"
              variant={filterValues.status === "running" ? "filled" : "outlined"}
              onClick={() => focusStatus(setFilters, filterValues, "running")}
            />
            <Chip
              label={`Failed ${statusCounts.failed}`}
              color="error"
              variant={filterValues.status === "failed" ? "filled" : "outlined"}
              onClick={() => focusStatus(setFilters, filterValues, "failed")}
            />
            <Chip
              label={`Completed ${statusCounts.completed}`}
              color="success"
              variant={filterValues.status === "completed" ? "filled" : "outlined"}
              onClick={() => focusStatus(setFilters, filterValues, "completed")}
            />
            <Chip
              label={`Cancelled ${statusCounts.cancelled}`}
              variant={filterValues.status === "cancelled" ? "filled" : "outlined"}
              onClick={() => focusStatus(setFilters, filterValues, "cancelled")}
            />
            <Chip
              label={`Showing ${runs.length} of ${total ?? runs.length} runs`}
              variant="outlined"
            />
            <Chip
              label={`Needs attention ${actionableRunCount}`}
              color="warning"
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
            {describeRunState(record)}
          </Typography>
          {record.status === "failed" && record.failure_reason ? (
            <Typography variant="caption" color="error.main" noWrap title={record.failure_reason}>
              Failure: {record.failure_reason}
            </Typography>
          ) : null}
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
            <Chip
              size="small"
              label={record.mode}
              color={record.mode === "production" ? "success" : "info"}
              variant="outlined"
              sx={{ alignSelf: "flex-start" }}
            />
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
