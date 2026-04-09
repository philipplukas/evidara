/**
 * Internal entity representing a document from OpenSearch.
 * This is NOT exposed via the API — the service layer transforms
 * it into a DetailView via mappers.
 */
export interface DocumentEntity {
  document_id: string;
  title: string;
  content?: string;
  content_docling?: unknown;
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
