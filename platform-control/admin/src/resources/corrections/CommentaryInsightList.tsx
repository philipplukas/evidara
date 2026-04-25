"use client";

/**
 * Browse view for commentary insights (#428).
 *
 * Lists overlay rows from `GET /v1/commentary-insights` (PR #440).
 * Operators jump from here into the editor (`CommentaryInsightShow`)
 * to raise a `field_edit` correction against an insight's claim.
 */

import { Datagrid, FunctionField, List, SelectInput, TextField } from "react-admin";
import { SwissDateField } from "../../components/SwissDateField";
import { ResourceName } from "../../domain/resourceNames";

const reviewStateChoices = [
  { id: "machine_generated_unreviewed", name: "Unreviewed" },
  { id: "machine_verified", name: "Machine verified" },
  { id: "editor_approved", name: "Editor approved" },
  { id: "rejected", name: "Rejected" },
  { id: "stale", name: "Stale" },
];

const insightFilters = [
  <SelectInput
    key="review_state"
    source="review_state"
    label="Review state"
    choices={reviewStateChoices}
    alwaysOn
  />,
];

export function CommentaryInsightList() {
  return (
    <List
      resource={ResourceName.CommentaryInsights}
      title="Commentary insights"
      perPage={50}
      sort={{ field: "updated_at", order: "DESC" }}
      filters={insightFilters}
    >
      <Datagrid bulkActionButtons={false} rowClick="show">
        <TextField source="insight_id" label="Insight ID" />
        <TextField source="document_id" label="Document" />
        <TextField source="insight_type" label="Type" />
        <FunctionField
          label="Claim"
          render={(record: unknown) => {
            if (!record || typeof record !== "object") return "";
            const r = record as { claim?: string };
            return r.claim ? r.claim.slice(0, 80) : "";
          }}
        />
        <TextField source="review_state" label="Review state" />
        <TextField source="overlay_revision" label="Rev" />
        <SwissDateField source="updated_at" label="Updated" showTime />
      </Datagrid>
    </List>
  );
}
