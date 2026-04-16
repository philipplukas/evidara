"use client";

import { Datagrid, EditButton, List, TextField } from "react-admin";
import { SwissDateField } from "../../components/SwissDateField";

export function AuthorityList() {
  return (
    <List resource="authorities" title="Authorities" perPage={50}>
      <Datagrid bulkActionButtons={false}>
        <TextField source="authority_id" label="Authority" />
        <TextField source="name" label="Name" />
        <TextField source="slug" label="Slug" />
        <TextField source="jurisdiction_id" label="Jurisdiction" emptyText="Global" />
        <SwissDateField source="updated_at" label="Updated" showTime />
        <EditButton />
      </Datagrid>
    </List>
  );
}
