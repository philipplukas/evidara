"use client";

import { Alert, Stack } from "@mui/material";
import { Create, required, SimpleForm, TextInput } from "react-admin";
import { ResourceName } from "../../domain/resourceNames";
import {
  ReferenceFormSection,
  referenceSlugHelperText,
  referenceSlugValidator,
} from "../shared/ReferenceInputs";

export function JurisdictionCreate() {
  return (
    <Create resource={ResourceName.Jurisdictions} title="Create Jurisdiction" redirect="list">
      <SimpleForm warnWhenUnsavedChanges sanitizeEmptyValues>
        <Stack spacing={2}>
          <Alert severity="info" variant="outlined">
            Jurisdiction records anchor the reference-data hierarchy. Keep the slug lowercase and
            stable because it is used in downstream labels and seeded content.
          </Alert>
          <ReferenceFormSection
            title="Identity"
            description="Choose a human-readable name and a slug that operators can keep using over time."
          >
            <TextInput
              source="name"
              label="Name"
              fullWidth
              helperText="Display name shown in lists and reference forms."
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
