"use client";

import {
  Datagrid,
  DateField,
  List,
  NumberField,
  SelectInput,
  TextField,
  TopToolbar,
} from "react-admin";
import { CancelRunButton } from "./RunActions";
import { RunLaunchButton } from "./RunLaunchDialog";

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

function RunListActions() {
  return (
    <TopToolbar>
      <RunLaunchButton label="Create Run" defaultMode="production" redirectResource="runs" />
    </TopToolbar>
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
      actions={<RunListActions />}
    >
      <Datagrid rowClick="show" bulkActionButtons={false}>
        <TextField source="run_id" label="Run" />
        <TextField source="source_name" label="Source" />
        <TextField source="version_label" label="Version" />
        <TextField source="mode" label="Mode" />
        <TextField source="status" label="Status" />
        <NumberField source="captured_resources_count" label="Captured" />
        <NumberField source="artifacts_count" label="Artifacts" />
        <DateField source="created_at" label="Created" showTime />
        <DateField source="updated_at" label="Updated" showTime />
        <CancelRunButton />
      </Datagrid>
    </List>
  );
}
