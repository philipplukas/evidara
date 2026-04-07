"use client";

import { Box, Typography } from "@mui/material";
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

function RunDurationField() {
  const record = useRecordContext<RunRecord>();
  if (!record?.started_at || !record?.completed_at) return <Typography variant="body2">-</Typography>;
  const ms = new Date(record.completed_at).getTime() - new Date(record.started_at).getTime();
  let display: string;
  if (ms < 1000) display = `${ms}ms`;
  else if (ms < 60000) display = `${(ms / 1000).toFixed(1)}s`;
  else display = `${Math.floor(ms / 60000)}m ${Math.round((ms % 60000) / 1000)}s`;
  return <Typography variant="body2">{display}</Typography>;
}

export function RunShow() {
  return (
    <Show resource="runs" title="Run Detail">
      <SimpleShowLayout>
        <Box sx={{ pb: 1 }}>
          <RunActionStack />
        </Box>
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
