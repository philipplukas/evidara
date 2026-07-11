/**
 * Shared form body for JurisdictionCreate + JurisdictionEdit.
 *
 * Mirrors `AuthorityForm.tsx`: same primitives, same validators, same
 * field ergonomics. The only difference from the authority form is the
 * field set (jurisdictions have `name` + `slug` only — no jurisdiction /
 * scope selection of their own). Edit passes `original` so the slug-change
 * alert can warn when the operator diverges from the persisted slug.
 */
"use client";

import { required } from "ra-core";
import { TextInput } from "../../ui/primitives";
import { ReferenceSlugChangeAlert, referenceSlugValidator } from "../shared/ReferenceFormFields";

type JurisdictionFormBodyProps = {
  idDisabled?: boolean;
  /** Persisted values, present on edit only. Drives the slug-change alert. */
  original?: { slug?: string | null };
};

export function JurisdictionFormBody({ idDisabled = false, original }: JurisdictionFormBodyProps) {
  return (
    <div className="space-y-5">
      {idDisabled ? (
        <TextInput
          source="jurisdiction_id"
          label="Jurisdiction ID"
          disabled
          helperText="Immutable identifier used by linked records."
        />
      ) : null}
      <TextInput
        source="name"
        label="Name"
        required
        validate={required()}
        helperText="Display name shown in lists and source forms."
        placeholder="e.g. Switzerland"
      />
      {original ? (
        <ReferenceSlugChangeAlert originalSlug={original.slug} entityLabel="Jurisdiction" />
      ) : null}
      <TextInput
        source="slug"
        label="Slug"
        required
        validate={[required(), referenceSlugValidator]}
        helperText="Use lowercase letters, numbers, and hyphens only. Keep the slug stable once records reference it."
        placeholder="e.g. ch"
      />
    </div>
  );
}
