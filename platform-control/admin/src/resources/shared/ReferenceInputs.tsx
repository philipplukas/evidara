"use client";

import { Alert } from "@mui/material";
import { SelectInput, useGetList, type Validator } from "react-admin";
import type { AuthorityRecord, JurisdictionRecord } from "../../lib/admin/dataProvider";
import {
  filterAuthoritiesByJurisdiction,
  formatReferenceLabel,
  isAuthorityValidForJurisdiction,
} from "./referenceUtils";

const LIST_PARAMS = {
  pagination: { page: 1, perPage: 250 },
  sort: { field: "name", order: "ASC" as const },
};

type JurisdictionSelectInputProps = {
  source: string;
  label: string;
  allowEmpty?: boolean;
  disabled?: boolean;
  helperText?: string;
  validate?: Validator | Validator[];
};

type AuthoritySelectInputProps = JurisdictionSelectInputProps & {
  jurisdictionId?: string | null;
};

const toValidatorList = (validate?: Validator | Validator[]): Validator[] => {
  if (!validate) {
    return [];
  }

  return Array.isArray(validate) ? validate : [validate];
};

export function JurisdictionSelectInput({
  source,
  label,
  allowEmpty = false,
  disabled = false,
  helperText,
  validate,
}: JurisdictionSelectInputProps) {
  const jurisdictions = useGetList<JurisdictionRecord>("jurisdictions", {
    ...LIST_PARAMS,
    filter: {},
  });

  if (jurisdictions.error) {
    return <Alert severity="error">Unable to load jurisdictions.</Alert>;
  }

  return (
    <SelectInput
      source={source}
      label={label}
      choices={(jurisdictions.data ?? []).map((jurisdiction) => ({
        id: jurisdiction.jurisdiction_id,
        name: formatReferenceLabel(jurisdiction),
      }))}
      isPending={jurisdictions.isPending}
      emptyText={allowEmpty ? "No jurisdiction" : undefined}
      emptyValue=""
      disabled={disabled}
      helperText={helperText}
      parse={(value) => (value === "" ? null : value)}
      format={(value) => value ?? ""}
      validate={validate}
    />
  );
}

export function AuthoritySelectInput({
  source,
  label,
  allowEmpty = false,
  disabled = false,
  helperText,
  jurisdictionId,
  validate,
}: AuthoritySelectInputProps) {
  const authorities = useGetList<AuthorityRecord>("authorities", {
    ...LIST_PARAMS,
    filter: {},
  });

  if (authorities.error) {
    return <Alert severity="error">Unable to load authorities.</Alert>;
  }

  const authorityRecords = authorities.data ?? [];
  const choices = filterAuthoritiesByJurisdiction(authorityRecords, jurisdictionId).map(
    (authority) => ({
      id: authority.authority_id,
      name: formatReferenceLabel(authority),
    }),
  );

  const validators = [
    ...toValidatorList(validate),
    (value: unknown) => {
      if (value === null || value === undefined || value === "") {
        return undefined;
      }

      if (typeof value !== "string") {
        return "Select a valid authority.";
      }

      if (!isAuthorityValidForJurisdiction(authorityRecords, value, jurisdictionId)) {
        return jurisdictionId
          ? "Select an authority within the chosen jurisdiction."
          : "Select a jurisdiction before choosing an authority.";
      }

      return undefined;
    },
  ];

  return (
    <SelectInput
      source={source}
      label={label}
      choices={choices}
      isPending={authorities.isPending}
      emptyText={allowEmpty ? "No authority" : undefined}
      emptyValue=""
      disabled={disabled || !jurisdictionId}
      helperText={
        helperText ??
        (jurisdictionId
          ? "Authority choices are filtered to the selected jurisdiction."
          : "Select a jurisdiction first to narrow the authority list.")
      }
      parse={(value) => (value === "" ? null : value)}
      format={(value) => value ?? ""}
      validate={validators}
    />
  );
}
