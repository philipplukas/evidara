#!/usr/bin/env npx tsx
/**
 * Seed script: Fetch Swiss court decisions from OpenCaseLaw (HuggingFace)
 * and transform them into the search-projection schema for OpenSearch.
 *
 * Usage:
 *   npx tsx scripts/seed-from-opencaselaw.ts              # Generate fixtures only
 *   npx tsx scripts/seed-from-opencaselaw.ts --index       # Generate + index into OpenSearch
 *   npx tsx scripts/seed-from-opencaselaw.ts --count 50    # Fetch 50 decisions (default: 20)
 *
 * Requirements:
 *   - No auth needed (public HuggingFace dataset)
 *   - OpenSearch running at localhost:9200 (only for --index)
 */

import { bootstrapDocumentsIndex } from '../src/core/opensearch/documents-bootstrap';

const HF_API =
  'https://datasets-server.huggingface.co/rows?dataset=voilaj/swiss-caselaw&config=default&split=train';

// ─── CLI args ───

const args = process.argv.slice(2);
const shouldIndex = args.includes('--index');
const countIdx = args.indexOf('--count');
const count = countIdx >= 0 ? parseInt(args[countIdx + 1], 10) : 20;
const offset = (() => {
  const i = args.indexOf('--offset');
  return i >= 0 ? parseInt(args[i + 1], 10) : 0;
})();

// ─── Types ───

interface OpenCaseLawRow {
  decision_id: string;
  court: string;
  canton: string;
  chamber: string | null;
  docket_number: string;
  decision_date: string;
  publication_date: string | null;
  language: string;
  title: string;
  legal_area: string | null;
  regeste: string | null;
  full_text: string | null;
  decision_type: string | null;
  cited_decisions: string | null; // JSON array as string
  source_url: string;
  bge_reference: string | null;
  has_full_text: boolean;
  text_length: number;
}

interface SearchProjection {
  document_id: string;
  title: string;
  jurisdiction: string;
  document_type: string;
  language: string;
  effective_date: string;
  structural_path?: string;
  content?: string;
  content_preview?: string;
  sections_count: number;
  citations_count: number;
  related_decisions_count: number;
  related_commentary_count: number;
  source_id?: string;
  processed_at: string;
  // Extra fields for richer display
  court?: string;
  docket_number?: string;
  regeste?: string;
}

// ─── Transform ───

function transformRow(row: OpenCaseLawRow): SearchProjection {
  // Parse cited decisions count
  let citedDecisions: string[] = [];
  if (row.cited_decisions) {
    try {
      citedDecisions = JSON.parse(row.cited_decisions);
    } catch {
      // malformed JSON — skip
    }
  }

  // Build structural path from legal area + court
  const pathParts: string[] = [];
  if (row.canton) pathParts.push(`Kanton ${row.canton}`);
  if (row.court) pathParts.push(formatCourtName(row.court));
  if (row.legal_area) pathParts.push(row.legal_area);
  const structuralPath = pathParts.length > 0 ? pathParts.join(' › ') : undefined;

  // Content preview from regeste or first 200 chars of full text
  const contentPreview =
    row.regeste?.slice(0, 200) ??
    row.full_text?.slice(0, 200) ??
    undefined;

  return {
    document_id: `doc_ocl_${sanitizeId(row.decision_id)}`,
    title: row.title || `${row.court} — ${row.docket_number}`,
    jurisdiction: 'CH',
    document_type: 'decision',
    language: row.language || 'de',
    effective_date: row.decision_date,
    structural_path: structuralPath,
    content: row.full_text ?? undefined,
    content_preview: contentPreview,
    sections_count: 0, // OpenCaseLaw doesn't have sections
    citations_count: citedDecisions.length,
    related_decisions_count: citedDecisions.length,
    related_commentary_count: 0,
    source_id: `src_opencaselaw`,
    processed_at: new Date().toISOString(),
    court: row.court,
    docket_number: row.docket_number,
    regeste: row.regeste ?? undefined,
  };
}

function sanitizeId(id: string): string {
  return id.replace(/[^a-zA-Z0-9_]/g, '_').slice(0, 64);
}

function formatCourtName(court: string): string {
  const parts = court.split('_');
  // e.g. "ag_anwaltskommission" → "AG Anwaltskommission"
  return parts
    .map((p, i) =>
      i === 0 ? p.toUpperCase() : p.charAt(0).toUpperCase() + p.slice(1),
    )
    .join(' ');
}

// ─── Fetch ───

async function fetchRows(
  offset: number,
  length: number,
): Promise<OpenCaseLawRow[]> {
  const url = `${HF_API}&offset=${offset}&length=${length}`;
  console.log(`Fetching ${length} rows from offset ${offset}...`);
  console.log(`  URL: ${url}`);

  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(
      `HuggingFace API error: ${response.status} ${response.statusText}`,
    );
  }

  const data = await response.json();
  return data.rows.map((r: { row: OpenCaseLawRow }) => r.row);
}

// ─── OpenSearch bulk index ───

async function bulkIndex(
  docs: SearchProjection[],
  indexName: string,
  nodeUrl: string,
): Promise<void> {
  console.log(`\nBulk-indexing ${docs.length} documents into ${indexName}...`);

  // Build NDJSON bulk body
  const lines: string[] = [];
  for (const doc of docs) {
    lines.push(JSON.stringify({ index: { _index: indexName, _id: doc.document_id } }));
    lines.push(JSON.stringify(doc));
  }
  const body = lines.join('\n') + '\n';

  const response = await fetch(`${nodeUrl}/_bulk`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-ndjson' },
    body,
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`OpenSearch bulk error: ${response.status} — ${text.slice(0, 500)}`);
  }

  const result = await response.json();
  const errors = result.items?.filter((i: { index: { error?: unknown } }) => i.index?.error) ?? [];
  if (errors.length > 0) {
    console.error(`  ${errors.length} indexing errors:`);
    for (const e of errors.slice(0, 3)) {
      console.error(`    ${JSON.stringify(e.index.error)}`);
    }
  } else {
    console.log(`  ✓ ${docs.length} documents indexed successfully`);
  }
}

// ─── Main ───

async function main() {
  console.log('═══════════════════════════════════════════════');
  console.log('  OpenCaseLaw → Evidara Search Projection Seed');
  console.log('═══════════════════════════════════════════════');
  console.log(`  Count:  ${count}`);
  console.log(`  Offset: ${offset}`);
  console.log(`  Index:  ${shouldIndex ? 'yes' : 'no (fixture only)'}`);
  console.log('');

  // 1. Bootstrap the OpenSearch index + aliases FIRST.
  //
  // This must happen before the HuggingFace fetch, and must not depend on it.
  // The demo corpus is a convenience; the index and the documents-read /
  // documents-write aliases are load-bearing — without them legal-search cannot
  // serve a search at all, and the projection path (document.processed -> write
  // alias) has nowhere to land. Bootstrapping first means an upstream outage
  // costs you the sample documents, not a working stack.
  const nodeUrl = process.env.OPENSEARCH_NODE ?? 'http://localhost:9200';
  const readAlias = process.env.OPENSEARCH_ALIAS_READ ?? 'documents-read';
  const writeAlias = process.env.OPENSEARCH_ALIAS_WRITE ?? 'documents-write';

  if (shouldIndex) {
    const bootstrap = await bootstrapDocumentsIndex({
      node: nodeUrl,
      readAlias,
      writeAlias,
      logger: { info: (m) => console.log(`  ${m}`), warn: (m) => console.warn(`  ${m}`) },
    });
    console.log(`  documents index bootstrap: ${bootstrap.status} (${bootstrap.physicalIndex})`);
  }

  // 2. Fetch the demo corpus from HuggingFace — best-effort.
  //
  // datasets-server.huggingface.co is a third party and does go down (observed
  // 503 for the whole dataset). Taking the entire local stack — and the nightly
  // CH Fedlex e2e, which seeds its own documents through the real pipeline and
  // does not need this corpus at all — down with it is the wrong trade.
  // Set SEED_REQUIRE_CORPUS=1 to make a fetch failure fatal instead.
  let rows: OpenCaseLawRow[];
  try {
    rows = await fetchRows(offset, count);
    console.log(`  Fetched ${rows.length} decisions`);
  } catch (err) {
    if (process.env.SEED_REQUIRE_CORPUS === '1') {
      throw err;
    }
    console.warn('');
    console.warn('  ⚠ Could not fetch the OpenCaseLaw demo corpus (upstream unavailable).');
    console.warn(`    ${err instanceof Error ? err.message : String(err)}`);
    console.warn('    The OpenSearch index and aliases are bootstrapped, so search and the');
    console.warn('    projection path still work — there just are no sample documents.');
    console.warn('    Re-run `npm run seed:index` once upstream recovers, or set');
    console.warn('    SEED_REQUIRE_CORPUS=1 to treat this as a hard failure.');
    console.warn('');
    return;
  }

  // Filter to rows with full text
  const withText = rows.filter((r) => r.has_full_text && r.full_text);
  console.log(`  ${withText.length} have full text`);

  // 2. Transform to projection schema
  const projections = withText.map(transformRow);
  console.log(`  Transformed ${projections.length} projections`);

  // 3. Write fixture file
  const fs = await import('fs');
  const path = await import('path');
  const fixtureDir = path.join(import.meta.dirname ?? __dirname, '..', 'fixtures');
  fs.mkdirSync(fixtureDir, { recursive: true });

  const fixturePath = path.join(fixtureDir, 'seed-projections.json');
  fs.writeFileSync(fixturePath, JSON.stringify(projections, null, 2));
  console.log(`\n  ✓ Fixtures written to ${fixturePath}`);

  // 4. Print sample
  const sample = projections[0];
  if (sample) {
    console.log('\n── Sample document ──');
    console.log(`  ID:           ${sample.document_id}`);
    console.log(`  Title:        ${sample.title}`);
    console.log(`  Jurisdiction: ${sample.jurisdiction}`);
    console.log(`  Language:     ${sample.language}`);
    console.log(`  Date:         ${sample.effective_date}`);
    console.log(`  Citations:    ${sample.citations_count}`);
    console.log(`  Path:         ${sample.structural_path}`);
    console.log(`  Content:      ${(sample.content?.length ?? 0)} chars`);
  }

  // 5. Optionally index into OpenSearch. The index and aliases were already
  // bootstrapped in step 1; write through the write alias so the read alias
  // serves the same documents.
  if (shouldIndex && projections.length > 0) {
    await bulkIndex(projections, writeAlias, nodeUrl);
  }

  // Stats summary
  console.log('\n── Summary ──');
  const langs = new Map<string, number>();
  const courts = new Map<string, number>();
  for (const p of projections) {
    langs.set(p.language, (langs.get(p.language) ?? 0) + 1);
    if (p.court) courts.set(p.court, (courts.get(p.court) ?? 0) + 1);
  }
  console.log(`  Languages:  ${[...langs.entries()].map(([k, v]) => `${k}(${v})`).join(', ')}`);
  console.log(`  Courts:     ${[...courts.entries()].slice(0, 5).map(([k, v]) => `${k}(${v})`).join(', ')}${courts.size > 5 ? ` +${courts.size - 5} more` : ''}`);
  console.log(`  Total docs: ${projections.length}`);
  console.log(`  With citations: ${projections.filter((p) => p.citations_count > 0).length}`);
  console.log('');
}

main().catch((err) => {
  console.error('Seed failed:', err);
  process.exit(1);
});
