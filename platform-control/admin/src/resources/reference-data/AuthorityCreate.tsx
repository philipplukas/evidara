"use client";

import { Alert, Stack } from "@mui/material";
import { Create, required, SimpleForm, TextInput } from "react-admin";
import {
  AuthorityScopeChangeAlert,
  JurisdictionSelectInput,
  ReferenceFormSection,
  referenceSlugHelperText,
  referenceSlugValidator,
} from "../shared/ReferenceInputs";

export function AuthorityCreate() {
  return (
    <Create resource="authorities" title="Create Authority" redirect="list">
      <SimpleForm warnWhenUnsavedChanges sanitizeEmptyValues>
        <Stack spacing={2}>
          <Alert severity="info" variant="outlined">
            Create a new authority that operators can reuse across sources. Leave jurisdiction blank
            only if this should be a global fallback for every jurisdiction.
          </Alert>
          <ReferenceFormSection
            title="Scope"
            description="Choose whether this authority is global or limited to one jurisdiction."
            tone="warning"
          >
            <JurisdictionSelectInput
              source="jurisdiction_id"
              label="Jurisdiction"
              allowEmpty
              helperText="Global authorities are shared everywhere. Scoped authorities only appear within the selected jurisdiction."
            />
            <AuthorityScopeChangeAlert />
          </ReferenceFormSection>
          <ReferenceFormSection
            title="Identity"
            description="Use a stable name for operators and a slug that will not need to change later."
          >
            <TextInput
              source="name"
              label="Name"
              fullWidth
              helperText="Display name shown in reference lists and operator forms."
              validate={required()}
            />
            <TextInput
              source="slug"
              label="Slug"
              fullWidth
              helperText={referenceSlugHelperText}
              validate={[required(), referenceSlugValidator]}
            />
          </ReferenceFormSection>
        </Stack>
      </SimpleForm>
    </Create>
  );
}
