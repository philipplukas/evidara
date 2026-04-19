"use client";

import { Alert, Stack } from "@mui/material";
import { Edit, required, SimpleForm, TextInput, useRecordContext } from "react-admin";
import { ResourceName } from "../../domain/resourceNames";
import type { JurisdictionRecord } from "../../lib/admin/dataProvider";
import {
  ReferenceFormSection,
  ReferenceSlugChangeAlert,
  referenceSlugHelperText,
  referenceSlugValidator,
} from "../shared/ReferenceInputs";

function JurisdictionEditFormBody() {
  const record = useRecordContext<JurisdictionRecord>();

  return (
    <Stack spacing={2}>
      <Alert severity="info" variant="outlined">
        Edit jurisdiction metadata carefully. A slug change can ripple into seeded records, operator
        notes, and any references that point to the old identifier.
      </Alert>
      <ReferenceFormSection
        title="Record identity"
        description="The jurisdiction ID is immutable, while the name and slug should stay easy to scan."
      >
        <TextInput
          source="jurisdiction_id"
          label="Jurisdiction ID"
          disabled
          fullWidth
          helperText="Immutable identifier used by linked records."
        />
        <TextInput
          source="name"
          label="Name"
          fullWidth
          helperText="Display name shown in lists and source forms."
          validate={required()}
        />
        <ReferenceSlugChangeAlert originalSlug={record?.slug} entityLabel="Jurisdiction" />
        <TextInput
          source="slug"
          label="Slug"
          fullWidth
          helperText={referenceSlugHelperText}
          validate={[required(), referenceSlugValidator]}
        />
      </ReferenceFormSection>
    </Stack>
  );
}

export function JurisdictionEdit() {
  return (
    <Edit resource={ResourceName.Jurisdictions} title="Edit Jurisdiction" redirect="list">
      <SimpleForm warnWhenUnsavedChanges sanitizeEmptyValues>
        <JurisdictionEditFormBody />
      </SimpleForm>
    </Edit>
  );
}
