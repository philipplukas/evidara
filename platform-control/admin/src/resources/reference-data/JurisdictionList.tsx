"use client";

import { Datagrid, EditButton, List, TextField } from "react-admin";
import { SwissDateField } from "../../components/SwissDateField";

export function JurisdictionList() {
  return (
    <List resource="jurisdictions" title="Jurisdictions" perPage={50}>
      <Datagrid bulkActionButtons={false}>
        <TextField source="jurisdiction_id" label="Jurisdiction" />
        <TextField source="name" label="Name" />
        <TextField source="slug" label="Slug" />
        <SwissDateField source="updated_at" label="Updated" showTime />
        <EditButton />
      </Datagrid>
    </List>
  );
}
