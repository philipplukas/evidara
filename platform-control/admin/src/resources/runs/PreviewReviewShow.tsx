"use client";

import { Box } from "@mui/material";
import { NumberField, Show, SimpleShowLayout, TextField } from "react-admin";
import { SwissDateField } from "../../components/SwissDateField";
import { RunActionStack } from "./RunActions";
import { RunDetailSections } from "./RunDetailSections";

export function PreviewReviewShow() {
  return (
    <Show
      resource="preview-review"
      title="Preview Review"
      queryOptions={{ meta: { mode: "preview" } }}
    >
      <SimpleShowLayout>
        <Box sx={{ pb: 1 }}>
          <RunActionStack />
        </Box>
        <TextField source="run_id" label="Run" />
        <TextField source="source_id" label="Source ID" />
        <TextField source="source_version_id" label="Source version ID" />
        <TextField source="status" label="Status" />
        <NumberField source="captured_resources_count" label="Captured resources" />
        <NumberField source="artifacts_count" label="Artifacts" />
        <TextField source="failure_reason" label="Failure reason" emptyText="-" />
        <SwissDateField source="started_at" label="Started" showTime emptyText="-" />
        <SwissDateField source="completed_at" label="Completed" showTime emptyText="-" />
        <SwissDateField source="created_at" label="Created" showTime />
        <SwissDateField source="updated_at" label="Updated" showTime />
        <RunDetailSections />
      </SimpleShowLayout>
    </Show>
  );
}
