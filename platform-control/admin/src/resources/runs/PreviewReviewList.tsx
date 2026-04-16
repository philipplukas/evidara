"use client";

import { Datagrid, List, NumberField, SelectInput, TextField, TopToolbar } from "react-admin";
import { SwissDateField } from "../../components/SwissDateField";
import { CancelRunButton } from "./RunActions";
import { RunLaunchButton } from "./RunLaunchDialog";

const previewFilters = [
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

function PreviewReviewActions() {
  return (
    <TopToolbar>
      <RunLaunchButton
        label="Create Preview Run"
        defaultMode="preview"
        allowedModes={["preview"]}
        redirectResource="preview-review"
      />
    </TopToolbar>
  );
}

export function PreviewReviewList() {
  return (
    <List
      resource="preview-review"
      title="Preview Review"
      perPage={25}
      sort={{ field: "created_at", order: "DESC" }}
      filter={{ mode: "preview" }}
      filters={previewFilters}
      actions={<PreviewReviewActions />}
    >
      <Datagrid rowClick="show" bulkActionButtons={false}>
        <TextField source="run_id" label="Run" />
        <TextField source="source_name" label="Source" />
        <TextField source="version_label" label="Version" />
        <TextField source="status" label="Status" />
        <NumberField source="captured_resources_count" label="Captured" />
        <NumberField source="artifacts_count" label="Artifacts" />
        <SwissDateField source="created_at" label="Created" showTime />
        <SwissDateField source="updated_at" label="Updated" showTime />
        <CancelRunButton />
      </Datagrid>
    </List>
  );
}
