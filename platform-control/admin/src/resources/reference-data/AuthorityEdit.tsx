"use client";

import { Alert, Stack } from "@mui/material";
import { Edit, required, SimpleForm, TextInput, useRecordContext } from "react-admin";
import { ResourceName } from "../../domain/resourceNames";
import type { AuthorityRecord } from "../../lib/admin/dataProvider";
import {
  AuthorityScopeChangeAlert,
  JurisdictionSelectInput,
  ReferenceFormSection,
  ReferenceSlugChangeAlert,
  referenceSlugHelperText,
  referenceSlugValidator,
} from "../shared/ReferenceInputs";

function AuthorityEditFormBody() {
  const record = useRecordContext<AuthorityRecord>();

  return (
    <Stack spacing={2}>
      <Alert severity="info" variant="outlined">
        Edit this authority carefully. Changing the slug or jurisdiction can affect what sources and
        forms can still point to this record.
      </Alert>
      <ReferenceFormSection
        title="Record identity"
        description="These fields describe the authoritative label operators see in the admin."
      >
        <TextInput
          source="authority_id"
          label="Authority ID"
          disabled
          fullWidth
          helperText="Immutable identifier used by linked records."
        />
        <TextInput
          source="name"
          label="Name"
          fullWidth
          helperText="Display name shown in reference lists and operator forms."
          validate={required()}
        />
        <ReferenceSlugChangeAlert originalSlug={record?.slug} entityLabel="Authority" />
        <TextInput
          source="slug"
          label="Slug"
          fullWidth
          helperText={referenceSlugHelperText}
          validate={[required(), referenceSlugValidator]}
        />
      </ReferenceFormSection>
      <ReferenceFormSection
        title="Scope"
        description="Global authorities are shared across every jurisdiction. Scoped authorities stay local."
        tone="warning"
      >
        <JurisdictionSelectInput
          source="jurisdiction_id"
          label="Jurisdiction"
          allowEmpty
          helperText="Leave blank only if the authority should remain global."
        />
        {record ? (
          <AuthorityScopeChangeAlert originalJurisdictionId={record.jurisdiction_id} />
        ) : null}
      </ReferenceFormSection>
    </Stack>
  );
}

export function AuthorityEdit() {
  return (
    <Edit resource={ResourceName.Authorities} title="Edit Authority" redirect="list">
      <SimpleForm warnWhenUnsavedChanges sanitizeEmptyValues>
        <AuthorityEditFormBody />
      </SimpleForm>
    </Edit>
  );
}
