import type { ConfigService } from '@nestjs/config';
import { describe, expect, it, vi } from 'vitest';
import { DocumentsOpenSearchAdapter } from './opensearch.adapter';

describe('DocumentsOpenSearchAdapter', () => {
  it('maps authority_name from OpenSearch documents', async () => {
    const search = vi.fn().mockResolvedValue({
      body: {
        hits: {
          hits: [
            {
              _source: {
                document_id: 'doc_001',
                title: 'Obligationenrecht',
                document_type: 'law',
                authority_name: 'Fedlex',
                official_citation: 'SR 101',
                is_official: true,
              },
            },
          ],
        },
      },
    });

    const adapter = new DocumentsOpenSearchAdapter(
      { search } as never,
      {
        get: (key: string) => {
          switch (key) {
            case 'opensearch.indexDocumentsRead':
              return 'documents-read-test';
            case 'opensearch.indexSections':
              return 'sections-test';
            case 'opensearch.indexCitations':
              return 'citations-test';
            default:
              return null;
          }
        },
      } as ConfigService,
    );

    await expect(adapter.getById('doc_001')).resolves.toEqual(
      expect.objectContaining({
        document_id: 'doc_001',
        authority_name: 'Fedlex',
        official_citation: 'SR 101',
        is_official: true,
      }),
    );
  });
});
