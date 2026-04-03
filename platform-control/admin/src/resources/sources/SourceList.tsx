"use client";

import { Datagrid, DateField, FunctionField, List, ReferenceField, TextField } from "react-admin";
import type { AuthorityRecord, JurisdictionRecord } from "../../lib/admin/dataProvider";
import { formatReferenceLabel } from "../shared/referenceUtils";

export function SourceList() {
  return (
    <List resource="sources" title="Sources" perPage={50}>
      <Datagrid rowClick="show" bulkActionButtons={false}>
        <TextField source="source_id" label="Source" />
        <TextField source="name" label="Name" />
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
        <TextField source="document_family" label="Family" emptyText="-" />
        <DateField source="updated_at" label="Updated" showTime />
      </Datagrid>
    </List>
  );
}
