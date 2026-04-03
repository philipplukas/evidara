"use client";

import { Box } from "@mui/material";
import { DateField, NumberField, Show, SimpleShowLayout, TextField } from "react-admin";
import { RunActionStack } from "./RunActions";
import { RunDetailSections } from "./RunDetailSections";

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
        <DateField source="created_at" label="Created" showTime />
        <DateField source="updated_at" label="Updated" showTime />
        <RunDetailSections />
      </SimpleShowLayout>
    </Show>
  );
}
