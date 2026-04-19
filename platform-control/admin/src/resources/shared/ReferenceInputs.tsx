"use client";

import { Alert, AlertTitle, Paper, Stack, Typography } from "@mui/material";
import type { ReactNode } from "react";
import { SelectInput, useGetList, type Validator } from "react-admin";
import { useWatch } from "react-hook-form";
import { ResourceName } from "../../domain/resourceNames";
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

type ReferenceSelectState = {
  severity: "info" | "warning" | "error";
  title: string;
  message: string;
};

type ReferenceFormSectionProps = {
  title: string;
  description: string;
  children: ReactNode;
  tone?: "default" | "warning";
};

type ReferenceSlugChangeAlertProps = {
  originalSlug?: string | null;
  entityLabel: string;
};

type AuthorityScopeChangeAlertProps = {
  originalJurisdictionId?: string | null;
};

const toValidatorList = (validate?: Validator | Validator[]): Validator[] => {
  if (!validate) {
    return [];
  }

  return Array.isArray(validate) ? validate : [validate];
};

export const REFERENCE_SLUG_PATTERN = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;

export const referenceSlugHelperText =
  "Use lowercase letters, numbers, and hyphens only. Keep the slug stable once records reference it.";

export const referenceSlugValidator: Validator = (value: unknown) => {
  if (value === null || value === undefined || value === "") {
    return undefined;
  }

  if (typeof value !== "string" || !REFERENCE_SLUG_PATTERN.test(value)) {
    return "Use lowercase letters, numbers, and hyphens only.";
  }

  return undefined;
};

export function ReferenceFormSection({
  title,
  description,
  children,
  tone = "default",
}: ReferenceFormSectionProps) {
  return (
    <Paper
      variant="outlined"
      sx={{
        p: 2,
        borderColor: tone === "warning" ? "warning.main" : "divider",
      }}
    >
      <Stack spacing={1.5}>
        <Stack spacing={0.25}>
          <Typography variant="overline" color="text.secondary">
            {title}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {description}
          </Typography>
        </Stack>
        {children}
      </Stack>
    </Paper>
  );
}

function ReferenceSelectStateAlert({ state }: { state: ReferenceSelectState }) {
  return (
    <Alert severity={state.severity} variant="outlined">
      <AlertTitle>{state.title}</AlertTitle>
      {state.message}
    </Alert>
  );
}

export function describeJurisdictionSelectState({
  isPending,
  hasError,
  choiceCount,
}: {
  isPending: boolean;
  hasError: boolean;
  choiceCount: number;
}): ReferenceSelectState | null {
  if (hasError) {
    return {
      severity: "error",
      title: "Unable to load jurisdictions",
      message: "Try again after the reference-data service recovers.",
    };
  }

  if (isPending && choiceCount === 0) {
    return {
      severity: "info",
      title: "Loading jurisdictions",
      message: "The selector will unlock once the jurisdiction list arrives.",
    };
  }

  if (!isPending && choiceCount === 0) {
    return {
      severity: "warning",
      title: "No jurisdictions available",
      message: "Seed at least one jurisdiction before creating or editing authorities.",
    };
  }

  return null;
}

export function describeAuthoritySelectState({
  isPending,
  hasError,
  choiceCount,
  jurisdictionId,
}: {
  isPending: boolean;
  hasError: boolean;
  choiceCount: number;
  jurisdictionId?: string | null;
}): ReferenceSelectState | null {
  if (hasError) {
    return {
      severity: "error",
      title: "Unable to load authorities",
      message: "Try again after the reference-data service recovers.",
    };
  }

  if (isPending && choiceCount === 0) {
    return {
      severity: "info",
      title: "Loading authorities",
      message: "The selector will unlock once the authority list arrives.",
    };
  }

  if (!isPending && choiceCount === 0) {
    return {
      severity: "warning",
      title: jurisdictionId ? "No matching authorities" : "No global authorities available",
      message: jurisdictionId
        ? "Create a scoped authority for this jurisdiction, or switch to a jurisdiction that already has one."
        : "Seed a global authority before continuing.",
    };
  }

  return null;
}

export function ReferenceSlugChangeAlert({
  originalSlug,
  entityLabel,
}: ReferenceSlugChangeAlertProps) {
  const currentSlug = useWatch({ name: "slug" }) as string | undefined;

  if (!originalSlug || !currentSlug || originalSlug === currentSlug) {
    return null;
  }

  return (
    <Alert severity="warning" variant="outlined">
      <AlertTitle>{entityLabel} slug changed</AlertTitle>
      Changing the slug from {originalSlug} to {currentSlug} can break seeded data, links, and
      operator notes that point at the old identifier.
    </Alert>
  );
}

export function AuthorityScopeChangeAlert({
  originalJurisdictionId,
}: AuthorityScopeChangeAlertProps) {
  const currentJurisdictionId = useWatch({ name: "jurisdiction_id" }) as string | null | undefined;

  if (originalJurisdictionId === undefined) {
    if (!currentJurisdictionId) {
      return (
        <Alert severity="warning" variant="outlined">
          <AlertTitle>Global authority</AlertTitle>
          Leaving jurisdiction blank makes this authority a global fallback that can be reused
          across every jurisdiction.
        </Alert>
      );
    }

    return (
      <Alert severity="info" variant="outlined">
        <AlertTitle>Scoped authority</AlertTitle>
        This authority will be scoped to the selected jurisdiction and will still show alongside
        global authorities where operators can pick either scope.
      </Alert>
    );
  }

  if (currentJurisdictionId === originalJurisdictionId) {
    return null;
  }

  if (!currentJurisdictionId) {
    return (
      <Alert severity="warning" variant="outlined">
        <AlertTitle>Global authority</AlertTitle>
        Leaving jurisdiction blank makes this authority a global fallback that can be reused across
        every jurisdiction.
      </Alert>
    );
  }

  return (
    <Alert severity="warning" variant="outlined">
      <AlertTitle>Authority scope changed</AlertTitle>
      Moving this authority into a jurisdiction changes where it appears in operator forms and may
      require downstream records to be reviewed.
    </Alert>
  );
}

export function JurisdictionSelectInput({
  source,
  label,
  allowEmpty = false,
  disabled = false,
  helperText,
  validate,
}: JurisdictionSelectInputProps) {
  const jurisdictions = useGetList<JurisdictionRecord>(ResourceName.Jurisdictions, {
    ...LIST_PARAMS,
    filter: {},
  });
  const choices = (jurisdictions.data ?? []).map((jurisdiction) => ({
    id: jurisdiction.jurisdiction_id,
    name: formatReferenceLabel(jurisdiction),
  }));
  const state = describeJurisdictionSelectState({
    isPending: jurisdictions.isPending,
    hasError: Boolean(jurisdictions.error),
    choiceCount: choices.length,
  });

  if (jurisdictions.error) {
    return (
      <ReferenceSelectStateAlert
        state={{
          severity: "error",
          title: "Unable to load jurisdictions",
          message: "Try again after the reference-data service recovers.",
        }}
      />
    );
  }

  return (
    <Stack spacing={1}>
      {state ? <ReferenceSelectStateAlert state={state} /> : null}
      <SelectInput
        source={source}
        label={label}
        choices={choices}
        isPending={jurisdictions.isPending}
        emptyText={allowEmpty ? "No jurisdiction" : undefined}
        emptyValue=""
        disabled={disabled}
        helperText={helperText}
        parse={(value) => (value === "" ? null : value)}
        format={(value) => value ?? ""}
        validate={validate}
      />
    </Stack>
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
  const authorities = useGetList<AuthorityRecord>(ResourceName.Authorities, {
    ...LIST_PARAMS,
    filter: {},
  });
  const authorityRecords = authorities.data ?? [];
  const choices = filterAuthoritiesByJurisdiction(authorityRecords, jurisdictionId).map(
    (authority) => ({
      id: authority.authority_id,
      name: formatReferenceLabel(authority),
    }),
  );
  const state = describeAuthoritySelectState({
    isPending: authorities.isPending,
    hasError: Boolean(authorities.error),
    choiceCount: choices.length,
    jurisdictionId,
  });

  if (authorities.error) {
    return (
      <ReferenceSelectStateAlert
        state={{
          severity: "error",
          title: "Unable to load authorities",
          message: "Try again after the reference-data service recovers.",
        }}
      />
    );
  }

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
          ? "Select an authority within the chosen jurisdiction or a global authority."
          : "Select a global authority or choose a jurisdiction first.";
      }

      return undefined;
    },
  ];

  return (
    <Stack spacing={1}>
      {state ? <ReferenceSelectStateAlert state={state} /> : null}
      <SelectInput
        source={source}
        label={label}
        choices={choices}
        isPending={authorities.isPending}
        emptyText={allowEmpty ? "No authority" : undefined}
        emptyValue=""
        disabled={disabled}
        helperText={
          helperText ??
          (jurisdictionId
            ? "Authority choices include the selected jurisdiction and global authorities."
            : "Authority choices are limited to global authorities until a jurisdiction is selected.")
        }
        parse={(value) => (value === "" ? null : value)}
        format={(value) => value ?? ""}
        validate={validators}
      />
    </Stack>
  );
}
