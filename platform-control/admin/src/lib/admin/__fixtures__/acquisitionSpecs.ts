/**
 * Acquisition-spec fixtures for tests.
 *
 * Every acquisition spec carries the `BaseAcquisitionSpec` fields — `tenant_id`,
 * `corpus_id`, `scope_type`, `source_origin_kind`, `trust_tier`,
 * `request_timeout_seconds`, `max_content_bytes` — and the server always sends
 * them, because each has a schema default. The admin's old hand-written union
 * typed them all optional, so fixtures omitted them and described a payload the
 * API never returns.
 *
 * Rather than paste seven fields into every spec fixture, tests state the
 * provider-specific fields they are about and let this fill in the base.
 */

import type { AcquisitionSpec } from "../dataProvider";

/** The base fields, at the schema defaults the server applies. */
export const BASE_ACQUISITION_SPEC_FIELDS = {
  tenant_id: "tenant_public",
  corpus_id: "corpus_public_default",
  scope_type: "global_public",
  source_origin_kind: "official_primary",
  trust_tier: "authoritative",
  language_codes: [],
  document_type_hint: null,
  request_timeout_seconds: 30,
  user_agent: null,
  max_content_bytes: 2_000_000,
} as const;

/**
 * Build a spec from its provider-specific fields.
 *
 * The cast is confined here on purpose: TypeScript cannot verify a spread
 * against an eleven-member discriminated union, and pushing that problem out to
 * every call site is what produced the `as unknown as AcquisitionSpec` casts
 * this replaces. Callers pass a real provider shape and get a real spec.
 */
export const buildAcquisitionSpec = (
  spec: { provider: AcquisitionSpec["provider"] } & Record<string, unknown>,
): AcquisitionSpec =>
  ({
    ...BASE_ACQUISITION_SPEC_FIELDS,
    ...spec,
  }) as unknown as AcquisitionSpec;
