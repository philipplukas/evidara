"use client";

import { Datagrid, DateField, EditButton, List, TextField } from "react-admin";

export function JurisdictionList() {
  return (
    <List resource="jurisdictions" title="Jurisdictions" perPage={50}>
      <Datagrid bulkActionButtons={false}>
        <TextField source="jurisdiction_id" label="Jurisdiction" />
        <TextField source="name" label="Name" />
        <TextField source="slug" label="Slug" />
        <DateField source="updated_at" label="Updated" showTime />
        <EditButton />
      </Datagrid>
    </List>
  );
}
