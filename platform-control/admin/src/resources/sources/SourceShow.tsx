"use client";

import {
  DateField,
  FunctionField,
  ReferenceField,
  Show,
  SimpleShowLayout,
  TextField,
} from "react-admin";
import type { AuthorityRecord, JurisdictionRecord } from "../../lib/admin/dataProvider";
import { formatReferenceLabel } from "../shared/referenceUtils";
import { SourceVersionsSection } from "./SourceVersionsSection";

export function SourceShow() {
  return (
    <Show resource="sources" title="Source">
      <SimpleShowLayout>
        <TextField source="source_id" label="Source ID" />
        <TextField source="name" label="Name" />
        <TextField source="description" label="Description" emptyText="-" />
        <TextField source="status" label="Status" />
        <ReferenceField
          source="jurisdiction_id"
          reference="jurisdictions"
          label="Jurisdiction"
          link={false}
        >
          <FunctionField<JurisdictionRecord> render={(record) => formatReferenceLabel(record)} />
        </ReferenceField>
        <ReferenceField
          source="authority_id"
          reference="authorities"
          label="Authority"
          link={false}
        >
          <FunctionField<AuthorityRecord> render={(record) => formatReferenceLabel(record)} />
        </ReferenceField>
        <TextField source="document_family" label="Document family" emptyText="-" />
        <TextField source="source_type" label="Source type" />
        <DateField source="created_at" label="Created" showTime />
        <DateField source="updated_at" label="Updated" showTime />
        <SourceVersionsSection />
      </SimpleShowLayout>
    </Show>
  );
}
