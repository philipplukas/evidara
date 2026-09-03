/**
 * Reading the run's provider-job payloads without pretending they are typed.
 *
 * `ProviderJobResponse.response_payload` is `additionalProperties: true` on the
 * contract (`contracts/api/platform-control.openapi.yaml`), and
 * `CapturedResourceResponse` has no refusal field at all. So the three things an
 * operator most needs off a run — what it *refused*, what it *captured versus
 * published*, and whether the *mirror was proven* — reach the panel today only as
 * pretty-printed JSON in the "Payloads" cell of `RunDetailSectionsV2`.
 *
 * This module parses that payload. It is deliberately the cheap version: a typed
 * field on the contract is the right one, and until it exists every value here is
 * labelled in the UI as read from an untyped payload.
 *
 * The honesty rules this module exists to keep (OPERATOR_JOBS.md, ADR-0042 §6):
 *
 * - **A missing number is `null`, never `0`.** `captured: null` means the provider
 *   did not record it. Rendering that as zero is the "lie the caller cannot
 *   detect". Every reader below must handle `null` as *unknown*.
 * - **`captured` and `published` are separate numbers.** #853: `_dispatch_run`
 *   flips the run to FAILED from `inline_failure_reason` while
 *   `_publish_pending_dispatch_events` publishes with no check on `run.status`, so
 *   a red run may already hold documents in the corpus. And in the other
 *   direction, the LexFind mirror check discards the whole batch unpublished
 *   (`lexfind_api_provider.py:1025-1035`) — which, with one number, "look[s] like
 *   an empty run" (its own comment, `:1055-1057`).
 * - **An unverified mirror check is not a passed one.** `source_unreachable`,
 *   `source_document_not_found` and `check_error` are *unverified*
 *   (`lexfind_api_provider.py:226-230`); only `identical` proves anything.
 *
 * Three provider shapes are in play on `main` and all three are read here:
 *
 * | producer | refusal list key | `skipped` |
 * |---|---|---|
 * | `lexfind_api_provider.py:1060` | `skipped` (array) | the array itself |
 * | `portal_http_provider_base.py:157` | `skipped_documents` | a count |
 * | `gemeinde_http_provider.py:420` | `skipped_manifestations` | a count |
 */

/** Keys under which a provider records its per-resource refusals. */
const REFUSAL_LIST_KEYS = ["skipped", "skipped_documents", "skipped_manifestations"] as const;

/**
 * Refusal slugs the acquisition side can emit, with what an operator does about
 * each. Ordered as `artifact_guard.check_capture` orders its checks
 * (`acquisition_core/artifact_guard.py:107-163`) — most specific first, so the
 * recorded reason names the actual defect and not a downstream symptom.
 *
 * `original_url_missing` is on this list because it is on `main`
 * (`lexfind_api_provider.py:1337`), notwithstanding the IA proposal's claim that
 * a repo-wide grep returns zero for it — that was true before #845 landed.
 *
 * An unknown slug is rendered as itself with no remedy rather than dropped: a
 * refusal the panel does not recognise is still a refusal.
 */
export const REFUSAL_REMEDIES: Record<string, string> = {
  empty_body: "The source returned zero bytes. Re-run, then check the source URL is still live.",
  content_type_mismatch:
    "The server declared a different type than the spec expects. Check the spec's expected content type against what the host actually serves.",
  html_where_binary_expected:
    "A redirect stub or login page dressed as a download (#716). The document was not fetched — do not read this as an empty source.",
  format_signature_missing:
    "The bytes carry no signature for the expected format. Treat as a corrupt or wrapped download, not as a missing document.",
  below_size_floor:
    "Smaller than the per-source floor. Either the floor is wrong for this corpus or the capture is a stub — read the byte count before widening the floor.",
  no_legal_text_markers:
    "The page reads as navigation or a JavaScript shell, not law (#631). The portal likely needs SPA rendering or a data endpoint.",
  unsupported_manifestation_content_type:
    "We cannot faithfully represent this manifestation, so the landing page was refused rather than substituted for the ordinance.",
  original_url_missing:
    "LexFind published no `original_url`, so capturing would have recorded the mirror as the document's own source. Refused rather than marked.",
};

export interface RefusalGroup {
  /** The slug exactly as the producer recorded it. */
  reason: string;
  count: number;
  /** What an operator does about it, or `null` for a slug this panel does not know. */
  remedy: string | null;
  /** First recorded detail sentence, for the operator who wants one example. */
  sampleDetail: string | null;
  /** First recorded URL, for the operator who wants to look at one. */
  sampleUrl: string | null;
}

/**
 * The capture ledger for one run: what the providers say they captured, and what
 * they say they published.
 *
 * `captured`/`published`/`refused` are `null` when no provider job recorded them.
 * `disagrees` is true only when **both** numbers are known and differ — an
 * unknown number can neither agree nor disagree, and must not be shown as either.
 */
export interface CaptureLedger {
  captured: number | null;
  published: number | null;
  refused: number | null;
  disagrees: boolean;
  /** True when at least one provider job recorded a refusal list we could read. */
  hasRefusalDetail: boolean;
}

export interface MirrorFidelityCheck {
  status: string;
  sourceUrl: string | null;
  detail: string | null;
  tolId: number | null;
  mirrorMd5: string | null;
  sourceMd5: string | null;
}

/**
 * The mirror-fidelity block `_spot_check_mirror_fidelity` writes
 * (`lexfind_api_provider.py:1549-1560`), read back.
 *
 * `proven` is the provider's own boolean and is *not* re-derived here: one
 * derivation, on the producing side, is the point of it existing.
 */
export interface MirrorFidelity {
  sampled: number | null;
  candidates: number | null;
  identical: number | null;
  diverged: number | null;
  unverified: number | null;
  proven: boolean;
  checks: MirrorFidelityCheck[];
}

/** Mirror-check statuses that prove nothing — `lexfind_api_provider.py:226-230`. */
export const MIRROR_STATUSES_UNVERIFIED = [
  "source_unreachable",
  "source_document_not_found",
  "check_error",
] as const;

export const isUnverifiedMirrorStatus = (status: string): boolean =>
  (MIRROR_STATUSES_UNVERIFIED as readonly string[]).includes(status);

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

/** A finite non-negative integer, or `null`. Never coerces; never defaults to 0. */
const readCount = (value: unknown): number | null =>
  typeof value === "number" && Number.isFinite(value) && value >= 0 ? Math.trunc(value) : null;

const readString = (value: unknown): string | null =>
  typeof value === "string" && value.trim().length > 0 ? value : null;

/** Add two counts where an unknown addend leaves the sum unknown-but-partial. */
const addCount = (total: number | null, next: number | null): number | null => {
  if (next === null) return total;
  return (total ?? 0) + next;
};

const refusalEntries = (payload: Record<string, unknown>): Record<string, unknown>[] => {
  const entries: Record<string, unknown>[] = [];
  for (const key of REFUSAL_LIST_KEYS) {
    const value = payload[key];
    if (!Array.isArray(value)) {
      // `skipped` is a *count* for the portal/gemeinde providers and a *list* for
      // LexFind. Only the list shape carries reasons.
      continue;
    }
    for (const entry of value) {
      if (isRecord(entry)) {
        entries.push(entry);
      }
    }
  }
  return entries;
};

/**
 * Group every recorded refusal across a run's provider jobs by its slug.
 *
 * Sorted by count descending, then slug, so the ordering is stable across renders
 * and the largest class leads. At municipal scale a queue is triaged per class,
 * not per item (ADR-0047 §6).
 */
export const groupRefusalsByReason = (payloads: unknown[]): RefusalGroup[] => {
  const byReason = new Map<string, RefusalGroup>();

  for (const payload of payloads) {
    if (!isRecord(payload)) continue;
    for (const entry of refusalEntries(payload)) {
      const reason = readString(entry.reason) ?? "unrecorded_reason";
      const existing = byReason.get(reason);
      if (existing) {
        existing.count += 1;
        existing.sampleDetail ??= readString(entry.detail);
        existing.sampleUrl ??= readString(entry.url);
        continue;
      }
      byReason.set(reason, {
        reason,
        count: 1,
        remedy: REFUSAL_REMEDIES[reason] ?? null,
        sampleDetail: readString(entry.detail),
        sampleUrl: readString(entry.url),
      });
    }
  }

  return [...byReason.values()].sort(
    (left, right) => right.count - left.count || left.reason.localeCompare(right.reason),
  );
};

/**
 * Sum the capture ledger across a run's provider jobs.
 *
 * A provider that records `captured` but not `published` leaves `published` at
 * `null` for the whole run: a partial sum presented as a total is the same defect
 * as a missing denominator rendered as zero.
 */
export const readCaptureLedger = (payloads: unknown[]): CaptureLedger => {
  let captured: number | null = null;
  let published: number | null = null;
  let refused: number | null = null;
  let anyPublishedRecorded = false;
  let hasRefusalDetail = false;

  for (const payload of payloads) {
    if (!isRecord(payload)) continue;

    captured = addCount(captured, readCount(payload.captured));

    const publishedCount = readCount(payload.published);
    if (publishedCount !== null) {
      anyPublishedRecorded = true;
      published = addCount(published, publishedCount);
    }

    const entries = refusalEntries(payload);
    if (entries.length > 0) {
      hasRefusalDetail = true;
      refused = addCount(refused, entries.length);
    } else {
      // The portal/gemeinde shape: a count with the list under another key we
      // already read above, so only take the number when there was no list.
      refused = addCount(refused, readCount(payload.skipped));
    }
  }

  return {
    captured,
    published: anyPublishedRecorded ? published : null,
    refused,
    // Unknown can neither agree nor disagree.
    disagrees: captured !== null && published !== null && captured !== published,
    hasRefusalDetail,
  };
};

const readCheck = (value: unknown): MirrorFidelityCheck | null => {
  if (!isRecord(value)) return null;
  const status = readString(value.status);
  if (!status) return null;
  return {
    status,
    sourceUrl: readString(value.source_url),
    detail: readString(value.detail),
    tolId: readCount(value.tol_id),
    mirrorMd5: readString(value.mirror_md5),
    sourceMd5: readString(value.source_md5),
  };
};

/**
 * The mirror-fidelity block, or `null` when no provider job carried one.
 *
 * `null` means **the check did not run**, which is a different statement from
 * "the mirror is identical" — the provider is explicit that an absent key "must
 * never read as verified" (`lexfind_api_provider.py:1461-1463`). The UI renders
 * the two differently and this function refuses to collapse them.
 */
export const readMirrorFidelity = (payloads: unknown[]): MirrorFidelity | null => {
  for (const payload of payloads) {
    if (!isRecord(payload)) continue;
    const block = payload.mirror_fidelity;
    if (!isRecord(block)) continue;

    const checks = Array.isArray(block.checks)
      ? block.checks.map(readCheck).filter((check): check is MirrorFidelityCheck => check !== null)
      : [];

    return {
      sampled: readCount(block.sampled),
      candidates: readCount(block.candidates),
      identical: readCount(block.identical),
      diverged: readCount(block.diverged),
      unverified: readCount(block.unverified),
      // The producer's boolean, not ours. `proven !== true` is unproven.
      proven: block.proven === true,
      checks,
    };
  }
  return null;
};
