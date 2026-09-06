/**
 * Deep links from a run's stage rows to the systems those rows name.
 *
 * Every row in `RunDetailSectionsV2` already carries the identifier that locates
 * its subject somewhere else — a `document_id` in the search index, an
 * `s3://` path in object storage — but they rendered as plain text, so the
 * operator's only move was to select, copy, and go find it by hand. The data was
 * there; the affordance was not.
 *
 * Two rules hold everywhere in this module, both load-bearing:
 *
 *  1. **An unconfigured target yields `null`, never a URL.** The tooling hosts
 *     are tailnet-only, so a hardcoded link is dead for anyone off the tailnet.
 *     Callers render plain text when they get `null`. A link that 404s is worse
 *     than the text it replaced, because it asserts the target is reachable.
 *  2. **An unparseable input yields `null`, never a guessed URL.** A storage
 *     path that is not `s3://bucket/key` is not coerced into one — see
 *     `parseS3Uri`.
 *
 * There is deliberately no log link. The cluster runs kube-prometheus-stack with
 * no Loki, so there is no run-scoped log query to link to; inventing one would
 * declare a capability that does not exist.
 */

/** Query parameter that selects the open document in legal-search. */
const SELECTED_ITEM_PARAM = "item";

/**
 * Bucket and key of an `s3://bucket/key` URI, or `null` when the input is not
 * one.
 *
 * `storage_path` is typed `str` (`platform_control/schemas/run.py:225`) with no
 * format constraint, so this must treat anything unexpected as unlinkable rather
 * than produce a console URL pointing at a bucket that does not exist.
 */
export function parseS3Uri(storagePath: string | null | undefined): {
  bucket: string;
  key: string;
} | null {
  const trimmed = storagePath?.trim();
  if (!trimmed?.startsWith("s3://")) {
    return null;
  }
  const withoutScheme = trimmed.slice("s3://".length);
  const separator = withoutScheme.indexOf("/");
  // A bucket with no key is a container, not an object — nothing to deep-link.
  if (separator <= 0) {
    return null;
  }
  const bucket = withoutScheme.slice(0, separator);
  const key = withoutScheme.slice(separator + 1);
  if (!bucket || !key) {
    return null;
  }
  return { bucket, key };
}

/** Strip one trailing slash so joins below never produce `//`. */
function normalizeBase(baseUrl: string | undefined): string | null {
  const trimmed = baseUrl?.trim();
  if (!trimmed) {
    return null;
  }
  return trimmed.endsWith("/") ? trimmed.slice(0, -1) : trimmed;
}

/**
 * Link to a document in legal-search, or `null` when the base URL is unset.
 *
 * The shape is legal-search's own: `/?item=<id>` (`lib/result-href.ts`), and the
 * id it selects on is the `document_id` — `search-result.mapper.ts:343` maps
 * `id: hit.document_id`. So a run's `document_id` is directly linkable with no
 * lookup, which is what makes "did this run's work actually reach a reader?"
 * a single click rather than a manual search.
 *
 * `legalSearchBaseUrlOrUndefined` is the right input, NOT `legalSearchBaseUrl`:
 * the latter defaults to `http://localhost:3101`, and linking a deployed admin
 * at localhost is the dead-link failure this module exists to avoid.
 */
export function buildDocumentSearchHref(
  legalSearchBaseUrl: string | undefined,
  documentId: string | null | undefined,
): string | null {
  const base = normalizeBase(legalSearchBaseUrl);
  const id = documentId?.trim();
  if (!base || !id) {
    return null;
  }
  return `${base}/?${SELECTED_ITEM_PARAM}=${encodeURIComponent(id)}`;
}

/**
 * Link to a raw artifact in the MinIO console object browser, or `null` when the
 * console base URL is unset or the path is not an `s3://` URI.
 *
 * The console's object browser route is `/browser/<bucket>/<encoded key>`. The
 * key is encoded whole — `encodeURIComponent` escapes `/` to `%2F`, which is
 * what the console expects for a nested prefix.
 */
export function buildMinioObjectHref(
  minioConsoleBaseUrl: string | undefined,
  storagePath: string | null | undefined,
): string | null {
  const base = normalizeBase(minioConsoleBaseUrl);
  const parsed = parseS3Uri(storagePath);
  if (!base || !parsed) {
    return null;
  }
  return `${base}/browser/${encodeURIComponent(parsed.bucket)}/${encodeURIComponent(parsed.key)}`;
}
