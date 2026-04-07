"use client";

import { Alert, MenuItem } from "@mui/material";
import { Create, FormDataConsumer, required, SelectInput, SimpleForm, TextInput } from "react-admin";
import { AuthoritySelectInput, JurisdictionSelectInput } from "../shared/ReferenceInputs";

const SOURCE_TYPE_CHOICES = [
  { id: "website", name: "Website (crawl)" },
  { id: "api", name: "API (structured)" },
];

export function SourceCreate() {
  return (
    <Create resource="sources" title="Create Source" redirect="show">
      <SimpleForm defaultValues={{ source_type: "website" }}>
        <Alert severity="info">
          Pick the legal boundary first. Authority choices are filtered by jurisdiction, while
          extractor profile and acquisition settings are frozen later on each source version.
        </Alert>
        <TextInput source="name" label="Name" validate={required()} />
        <TextInput
          source="description"
          label="Description"
          multiline
          helperText="Optional internal notes for operators reviewing this source."
        />
        <JurisdictionSelectInput
          source="jurisdiction_id"
          label="Jurisdiction"
          helperText="Choose the legal boundary this source belongs to."
          validate={required()}
        />
        <FormDataConsumer<{ jurisdiction_id?: string | null }>>
          {({ formData }) => (
            <AuthoritySelectInput
              key={formData.jurisdiction_id ?? "no-jurisdiction"}
              source="authority_id"
              label="Authority"
              jurisdictionId={formData.jurisdiction_id ?? null}
              helperText={
                formData.jurisdiction_id
                  ? "Only authorities in the selected jurisdiction are shown."
                  : "Select a jurisdiction first to load the matching authorities."
              }
              validate={required()}
            />
          )}
        </FormDataConsumer>
        <TextInput
          source="document_family"
          label="Document family"
          helperText="Optional grouping label surfaced during operator review."
        />
        <SelectInput
          source="source_type"
          label="Source type"
          choices={SOURCE_TYPE_CHOICES}
          helperText="Website for Firecrawl crawls, API for structured endpoints like RIS OGD."
          validate={required()}
        />
      </SimpleForm>
    </Create>
  );
}
