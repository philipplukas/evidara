/**
 * Internal entity representing a document from OpenSearch.
 * This is NOT exposed via the API — the service layer transforms
 * it into a DetailView via mappers.
 */
export interface DocumentEntity {
  document_id: string;
  title: string;
  /**
   * The document body, as a plain-text string. `ProjectionsService` writes it
   * from document-intelligence's `body_text`/`full_text` (both `str` in
   * `canonical/models.py`), and the index maps it as `text` — so a structured
   * object can never live here. There is deliberately no `content_docling`
   * sibling: nothing in the pipeline produces a DoclingDocument (ADR-0010 is
   * still `Proposed`), the index has no such field, and the Document Service's
   * `/lean` payload is a canonical row, not a DoclingDocument.
   */
  content?: string;
  /**
   * The official headnote (Regeste) of a court decision — prose, not a label.
   * Mapped as `text` in `core/opensearch/documents-index.mapping.ts` and
   * boosted by the search adapter, so a search snippet could quote it long
   * before the detail response could return it (#760).
   *
   * Often absent, and legitimately so: only a decision has a headnote, and the
   * projection writes one only when the source itself published it — the Swiss
   * `Regeste`, the Austrian `Rechtssatz`/`Leitsatz`, promoted by
   * document-intelligence onto `metadata.regeste` (#836). Statutes and
   * ordinances carry none, and a decision whose source published none carries
   * none rather than an invented summary.
   */
  regeste?: string;
  jurisdiction?: string;
  document_type?: string;
  authority_name?: string;
  official_citation?: string;
  original_language?: string;
  translation_status?: 'original' | 'machine_translated' | 'translation_unavailable';
  is_official?: boolean;
  effective_date?: string;
  lifecycle_status?: string;
  source_id?: string;
  processed_at?: string;
  structural_path?: string;
  language?: string;
  sections_count?: number;
  citations_count?: number;
  parent_section_id?: string;
}

/**
 * Internal entity representing a document section from OpenSearch.
 */
export interface SectionEntity {
  section_id: string;
  document_id: string;
  title?: string;
  ordinal?: number;
  depth?: number;
  content_preview?: string;
  parent_section_id?: string;
}

/**
 * Internal entity representing a citation from OpenSearch.
 */
export interface CitationEntity {
  citation_id: string;
  source_document_id: string;
  source_section_id?: string;
  target_document_id?: string;
  target_title?: string;
  target_subtitle?: string;
  target_document_type?: string;
  citation_text: string;
  citation_type?: string;
  resolved: boolean;
}
