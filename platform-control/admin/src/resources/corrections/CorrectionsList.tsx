"use client";

/**
 * Operator queue for HITL corrections (#428).
 *
 * Lists corrections in newest-first order; the default filter pins the
 * queue to `status=pending` so operators see what needs action first.
 * The dataProvider talks to `GET /v1/corrections` (PR #440); column
 * shape mirrors the contract envelope frozen in PR #434.
 */

import { Datagrid, FunctionField, List, SelectInput, TextField } from "react-admin";
import { SwissDateField } from "../../components/SwissDateField";
import { ResourceName } from "../../domain/resourceNames";

const correctionStatusChoices = [
  { id: "pending", name: "Pending" },
  { id: "applied", name: "Applied" },
  { id: "rejected", name: "Rejected" },
  { id: "superseded", name: "Superseded" },
];

const correctionTypeChoices = [
  { id: "field_edit", name: "Field edit" },
  { id: "annotation", name: "Annotation" },
  { id: "reject", name: "Reject" },
  { id: "rescore_request", name: "Rescore request" },
];

const targetEntityTypeChoices = [
  { id: "source", name: "Source" },
  { id: "document", name: "Document" },
  { id: "commentary_insight", name: "Commentary insight" },
];

const correctionFilters = [
  <SelectInput
    key="status"
    source="status"
    label="Status"
    choices={correctionStatusChoices}
    alwaysOn
  />,
  <SelectInput
    key="correction_type"
    source="correction_type"
    label="Type"
    choices={correctionTypeChoices}
  />,
  <SelectInput
    key="target_entity_type"
    source="target_entity_type"
    label="Target type"
    choices={targetEntityTypeChoices}
  />,
];

export function CorrectionsList() {
  return (
    <List
      resource={ResourceName.Corrections}
      title="Corrections queue"
      perPage={50}
      sort={{ field: "created_at", order: "DESC" }}
      filters={correctionFilters}
      filterDefaultValues={{ status: "pending" }}
    >
      <Datagrid bulkActionButtons={false} rowClick="show">
        <TextField source="correction_id" label="ID" />
        <TextField source="status" label="Status" />
        <TextField source="correction_type" label="Type" />
        <TextField source="target_entity_type" label="Target" />
        <TextField source="target_entity_id" label="Target ID" />
        <FunctionField
          label="Rationale"
          render={(record: unknown) => {
            if (!record || typeof record !== "object") return "";
            const r = record as { rationale?: string | null };
            return r.rationale ?? "";
          }}
        />
        <SwissDateField source="created_at" label="Created" showTime />
      </Datagrid>
    </List>
  );
}
