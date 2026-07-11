/**
 * Shared form body for AuthorityCreate + AuthorityEdit.
 *
 * Encapsulates the validators and field set so create and edit render
 * identical UI and diverge only in the wiring (save function, defaults) and in
 * the change-detection alerts, which need the persisted record. Edit passes
 * `original`; create leaves it undefined so the scope alert describes
 * global-vs-scoped instead of warning about a change.
 */
"use client";

import { required } from "ra-core";
import { TextInput } from "../../ui/primitives";
import {
  AuthorityScopeChangeAlert,
  JurisdictionSelectField,
  ReferenceSlugChangeAlert,
  referenceSlugValidator,
} from "../shared/ReferenceFormFields";

type AuthorityFormBodyProps = {
  idDisabled?: boolean;
  /** Persisted values, present on edit only. Drives the change-detection alerts. */
  original?: { slug?: string | null; jurisdiction_id?: string | null };
};

export function AuthorityFormBody({ idDisabled = false, original }: AuthorityFormBodyProps) {
  return (
    <div className="space-y-5">
      {idDisabled ? (
        <TextInput
          source="authority_id"
          label="Authority ID"
          disabled
          helperText="Immutable identifier used by linked records."
        />
      ) : null}
      <TextInput
        source="name"
        label="Name"
        required
        validate={required()}
        helperText="Display name shown in reference lists and operator forms."
        placeholder="e.g. Bundesgericht"
      />
      {original ? (
        <ReferenceSlugChangeAlert originalSlug={original.slug} entityLabel="Authority" />
      ) : null}
      <TextInput
        source="slug"
        label="Slug"
        required
        validate={[required(), referenceSlugValidator]}
        helperText="Use lowercase letters, numbers, and hyphens only. Keep the slug stable once records reference it."
        placeholder="e.g. bger"
      />
      <JurisdictionSelectField />
      <AuthorityScopeChangeAlert
        originalJurisdictionId={original ? (original.jurisdiction_id ?? null) : undefined}
      />
    </div>
  );
}
