"use client";

import type { AuthorityRecord } from "../../lib/admin/dataProvider";

type ReferenceLabelRecord = {
  name: string;
  slug: string;
};

export const formatReferenceLabel = (record: ReferenceLabelRecord | null | undefined): string =>
  record ? `${record.name} (${record.slug})` : "—";

export const filterAuthoritiesByJurisdiction = (
  authorities: AuthorityRecord[],
  jurisdictionId?: string | null,
): AuthorityRecord[] =>
  jurisdictionId
    ? authorities.filter((authority) => authority.jurisdiction_id === jurisdictionId)
    : authorities;

export const isAuthorityValidForJurisdiction = (
  authorities: AuthorityRecord[],
  authorityId: string | null | undefined,
  jurisdictionId?: string | null,
): boolean => {
  if (!authorityId) {
    return true;
  }

  if (!jurisdictionId) {
    return false;
  }

  return authorities.some(
    (authority) =>
      authority.authority_id === authorityId && authority.jurisdiction_id === jurisdictionId,
  );
};
