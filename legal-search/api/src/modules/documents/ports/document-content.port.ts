/**
 * Port for fetching structured document body (lean Docling JSON) from document-intelligence.
 * When DOCUMENT_INTELLIGENCE_BASE_URL is unset, a no-op implementation is used.
 */

export const DOCUMENT_CONTENT_PORT = Symbol('DOCUMENT_CONTENT_PORT');

export interface DocumentContentPort {
  /**
   * Fetches lean DoclingDocument JSON for the given document revision.
   * Returns `undefined` when the integration is disabled, the upstream returns 404,
   * or the request fails (errors are logged by the implementation).
   */
  fetchLeanContent(documentId: string, processingManifestId?: string): Promise<unknown | undefined>;
}
