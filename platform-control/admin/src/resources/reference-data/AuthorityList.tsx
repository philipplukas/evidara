"use client";

import { Datagrid, DateField, EditButton, List, TextField } from "react-admin";

export function AuthorityList() {
  return (
    <List resource="authorities" title="Authorities" perPage={50}>
      <Datagrid bulkActionButtons={false}>
        <TextField source="authority_id" label="Authority" />
        <TextField source="name" label="Name" />
        <TextField source="slug" label="Slug" />
        <TextField source="jurisdiction_id" label="Jurisdiction" emptyText="Global" />
        <DateField source="updated_at" label="Updated" showTime />
        <EditButton />
      </Datagrid>
    </List>
  );
}
