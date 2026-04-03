"use client";

import { Edit, required, SimpleForm, TextInput } from "react-admin";
import { JurisdictionSelectInput } from "../shared/ReferenceInputs";

export function AuthorityEdit() {
  return (
    <Edit resource="authorities" title="Edit Authority" redirect="list">
      <SimpleForm>
        <TextInput source="authority_id" label="Authority ID" disabled fullWidth />
        <JurisdictionSelectInput source="jurisdiction_id" label="Jurisdiction" allowEmpty />
        <TextInput source="name" label="Name" validate={required()} />
        <TextInput source="slug" label="Slug" validate={required()} />
      </SimpleForm>
    </Edit>
  );
}
