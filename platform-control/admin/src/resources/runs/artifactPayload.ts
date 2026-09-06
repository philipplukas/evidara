/**
 * Reading a raw artifact's payload without reading JSON.
 *
 * A raw artifact's `artifact_metadata` is the whole captured page payload, and
 * the admin rendered it as one `JSON.stringify(…, null, 2)` block in a table
 * cell. For a Firecrawl page that carries the full document body, that is a wall
 * of escaped text in a `<pre>` — every fact an operator wants (which URL, what
 * status, how many bytes, what did we actually get) is present and none of it is
 * legible.
 *
 * Worth being precise about what this payload is, because it is easy to assume
 * otherwise: platform-control's artifact store holds **no document bytes**. Both
 * writers persist this same JSON object — `firecrawl_webhook_service.py:303-316`
 * passes `page` to both the DB column and `store_page_payload`, and
 * `run_service.py:1523-1528` does the same with `raw_record.metadata`. The row's
 * `content_type` is the *upstream* type (often `application/pdf`) while the
 * stored object is JSON. So there is nothing to fetch that is not already here:
 * this module makes what we hold readable rather than reaching for more.
 *
 * Everything here is defensive. The payload is provider-shaped JSON with no
 * schema on our side, so every accessor treats a missing, null or wrongly-typed
 * value as absent rather than throwing or coercing.
 */

/** A labelled fact lifted out of the payload for the summary rows. */
export interface ArtifactPayloadField {
  readonly label: string;
  readonly value: string;
}

/** The document body found in a payload, and how it was encoded. */
export interface ArtifactPayloadContent {
  /** Which key it came from — shown to the operator so the view is not a guess. */
  readonly key: string;
  readonly value: string;
}

function asRecord(value: unknown): Record<string, unknown> | null {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return null;
  }
  return value as Record<string, unknown>;
}

/**
 * A scalar rendered as a string, or `null` when the value is absent or is a
 * container. Booleans and numbers are kept — `statusCode: 0` and `ok: false`
 * are meaningful, so a truthiness check would wrongly drop them.
 */
function asScalarString(value: unknown): string | null {
  if (typeof value === "string") {
    const trimmed = value.trim();
    return trimmed === "" ? null : trimmed;
  }
  if (typeof value === "number" && Number.isFinite(value)) {
    return String(value);
  }
  if (typeof value === "boolean") {
    return String(value);
  }
  return null;
}

/**
 * Keys worth surfacing, in display order, paired with the label to show.
 *
 * Looked up at the payload's top level AND inside a nested `metadata` object,
 * because Firecrawl nests the interesting fields one level down
 * (`page.metadata.sourceURL`) while the normalized path keeps them flat.
 * First hit wins, top level first.
 */
const SUMMARY_KEYS: ReadonlyArray<readonly [key: string, label: string]> = [
  ["title", "Title"],
  ["sourceURL", "Source URL"],
  ["url", "URL"],
  ["statusCode", "HTTP status"],
  ["contentType", "Content type"],
  ["language", "Language"],
  ["byte_size", "Byte size"],
  ["checksum", "Checksum"],
  ["checksum_algorithm", "Checksum algorithm"],
];

/** Keys that may carry the document body, in the order we prefer them. */
const CONTENT_KEYS: readonly string[] = ["markdown", "content", "text", "html", "rawHtml"];

/**
 * The labelled facts an operator reads first, lifted out of an arbitrary
 * payload. Absent keys are omitted rather than rendered as em-dashes — a
 * summary row for a field the provider never sent is noise, not information.
 */
export function summarizeArtifactPayload(payload: unknown): ArtifactPayloadField[] {
  const root = asRecord(payload);
  if (!root) {
    return [];
  }
  const nested = asRecord(root.metadata);

  const fields: ArtifactPayloadField[] = [];
  for (const [key, label] of SUMMARY_KEYS) {
    const value = asScalarString(root[key]) ?? (nested ? asScalarString(nested[key]) : null);
    if (value !== null) {
      fields.push({ label, value });
    }
  }
  return fields;
}

/**
 * The document body, or `null` when the payload carries none.
 *
 * Returns the key it came from so the UI can say "markdown" or "rawHtml"
 * explicitly. An operator reading a body needs to know which representation
 * they are looking at; silently preferring one and not saying so turns a
 * provider difference into an invisible one.
 */
export function extractArtifactContent(payload: unknown): ArtifactPayloadContent | null {
  const root = asRecord(payload);
  if (!root) {
    return null;
  }
  for (const key of CONTENT_KEYS) {
    const value = root[key];
    if (typeof value === "string" && value.trim() !== "") {
      return { key, value };
    }
  }
  return null;
}

/**
 * Keys already accounted for by the summary and the content block, so the
 * "everything else" view can omit them instead of repeating them.
 */
export function consumedPayloadKeys(payload: unknown): Set<string> {
  const consumed = new Set<string>();
  const root = asRecord(payload);
  if (!root) {
    return consumed;
  }
  for (const [key] of SUMMARY_KEYS) {
    if (key in root) {
      consumed.add(key);
    }
  }
  const content = extractArtifactContent(payload);
  if (content) {
    consumed.add(content.key);
  }
  return consumed;
}

/**
 * The payload minus what the summary and content block already showed, or
 * `null` when nothing is left.
 *
 * `metadata` is deliberately NOT removed even when the summary drew from it:
 * only a handful of its keys are lifted, and dropping the whole object would
 * hide the rest. Showing it twice is better than hiding it once.
 */
export function remainingPayload(payload: unknown): Record<string, unknown> | null {
  const root = asRecord(payload);
  if (!root) {
    return null;
  }
  const consumed = consumedPayloadKeys(payload);
  const rest = Object.fromEntries(Object.entries(root).filter(([key]) => !consumed.has(key)));
  return Object.keys(rest).length > 0 ? rest : null;
}
