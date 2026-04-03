"use client";

import { Create, required, SimpleForm, TextInput } from "react-admin";
import { JurisdictionSelectInput } from "../shared/ReferenceInputs";

export function AuthorityCreate() {
  return (
    <Create resource="authorities" title="Create Authority" redirect="list">
      <SimpleForm>
        <JurisdictionSelectInput source="jurisdiction_id" label="Jurisdiction" allowEmpty />
        <TextInput source="name" label="Name" validate={required()} />
        <TextInput source="slug" label="Slug" validate={required()} />
      </SimpleForm>
    </Create>
  );
}
