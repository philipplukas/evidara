/**
 * Domain errors for the search module.
 *
 * The search repository contract has exactly two outcomes:
 *  - it returns a `SearchResultEntity` — the query *executed*; `total: 0`
 *    then genuinely means "zero matches";
 *  - it throws `SearchBackendUnavailableError` — the query *could not be
 *    executed* (missing index/alias, connection refused, timeout).
 *
 * Collapsing the second case into `{ total: 0, hits: [] }` is what made a
 * cluster with no document index at all look like a product with no
 * matching documents (see #551). Failures must stay loud: the adapter
 * logs at ERROR and throws, and `AllExceptionsFilter` maps this error to
 * a 503.
 */

/** Why the query could not be executed. */
export type SearchFailureReason = 'index_missing' | 'unavailable';

type OpenSearchErrorLike = {
  statusCode?: number;
  body?: { error?: { type?: string; reason?: string } };
  meta?: { statusCode?: number; body?: { error?: { type?: string; reason?: string } } };
};

function asOpenSearchError(err: unknown): OpenSearchErrorLike {
  return (err ?? {}) as OpenSearchErrorLike;
}

function errorType(err: unknown): string | undefined {
  const candidate = asOpenSearchError(err);
  return candidate.meta?.body?.error?.type ?? candidate.body?.error?.type;
}

function statusCode(err: unknown): number | undefined {
  const candidate = asOpenSearchError(err);
  return candidate.meta?.statusCode ?? candidate.statusCode;
}

/**
 * True when OpenSearch answered "that index/alias does not exist" — the
 * failure mode behind #551. Recognised both from the structured client
 * error (`meta.body.error.type`) and from the raw message, so a wrapped
 * or re-thrown error is still classified correctly.
 */
export function isIndexMissingError(err: unknown): boolean {
  if (errorType(err) === 'index_not_found_exception') return true;
  const message = err instanceof Error ? err.message : String(err ?? '');
  if (message.includes('index_not_found_exception')) return true;
  return statusCode(err) === 404;
}

/** Human-readable one-liner for logs and health payloads. */
export function describeOpenSearchError(err: unknown): string {
  const candidate = asOpenSearchError(err);
  const reason = candidate.meta?.body?.error?.reason ?? candidate.body?.error?.reason;
  const type = errorType(err);
  const message = err instanceof Error ? err.message : undefined;
  if (type && reason) return `${type}: ${reason}`;
  if (type) return message && !message.includes(type) ? `${type}: ${message}` : type;
  return message ?? String(err ?? 'unknown error');
}

/**
 * The search backend could not execute the query. Distinct from a query
 * that executed and matched nothing.
 */
export class SearchBackendUnavailableError extends Error {
  readonly reason: SearchFailureReason;
  readonly operation: string;
  readonly index: string;
  readonly detail: string;

  constructor(operation: string, index: string, cause: unknown) {
    const reason: SearchFailureReason = isIndexMissingError(cause)
      ? 'index_missing'
      : 'unavailable';
    const detail = describeOpenSearchError(cause);
    super(
      reason === 'index_missing'
        ? `Search index "${index}" does not exist — ${operation} cannot be served (${detail})`
        : `Search backend unavailable for ${operation} on "${index}" (${detail})`,
    );
    this.name = 'SearchBackendUnavailableError';
    this.reason = reason;
    this.operation = operation;
    this.index = index;
    this.detail = detail;
    this.cause = cause;
  }
}
