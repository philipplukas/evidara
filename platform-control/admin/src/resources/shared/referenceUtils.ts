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
  authorities.filter((authority) =>
    jurisdictionId
      ? authority.jurisdiction_id === jurisdictionId || authority.jurisdiction_id === null
      : authority.jurisdiction_id === null,
  );

export const isAuthorityValidForJurisdiction = (
  authorities: AuthorityRecord[],
  authorityId: string | null | undefined,
  jurisdictionId?: string | null,
): boolean => {
  if (!authorityId) {
    return true;
  }

  return authorities.some(
    (authority) =>
      authority.authority_id === authorityId &&
      (jurisdictionId
        ? authority.jurisdiction_id === jurisdictionId || authority.jurisdiction_id === null
        : authority.jurisdiction_id === null),
  );
};
