"use client";

import { Create, required, SimpleForm, TextInput } from "react-admin";

export function JurisdictionCreate() {
  return (
    <Create resource="jurisdictions" title="Create Jurisdiction" redirect="list">
      <SimpleForm>
        <TextInput source="name" label="Name" validate={required()} />
        <TextInput source="slug" label="Slug" validate={required()} />
      </SimpleForm>
    </Create>
  );
}
