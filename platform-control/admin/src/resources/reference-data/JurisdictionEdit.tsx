"use client";

import { Edit, required, SimpleForm, TextInput } from "react-admin";

export function JurisdictionEdit() {
  return (
    <Edit resource="jurisdictions" title="Edit Jurisdiction" redirect="list">
      <SimpleForm>
        <TextInput source="jurisdiction_id" label="Jurisdiction ID" disabled fullWidth />
        <TextInput source="name" label="Name" validate={required()} />
        <TextInput source="slug" label="Slug" validate={required()} />
      </SimpleForm>
    </Edit>
  );
}
