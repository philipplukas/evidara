/**
 * Stable `iconKey` strings for search/detail metadata rows (BFF → frontend registry).
 * Keep in sync with `legal-search/frontend/src/lib/icons.ts`.
 */
export function iconKeyForDocumentType(type: string): string | undefined {
  switch (type) {
    case 'law':
      return 'dtype-law';
    case 'decision':
      return 'dtype-decision';
    case 'commentary':
      return 'dtype-commentary';
    case 'rechtssatz':
      return 'dtype-rechtssatz';
    default:
      return undefined;
  }
}

export const METADATA_ROW_ICONS = {
  status: 'meta-status',
  calendar: 'meta-calendar',
  citation: 'meta-citation',
  official: 'meta-official',
  language: 'meta-language',
  authority: 'meta-authority',
} as const;
