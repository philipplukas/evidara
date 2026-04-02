#!/usr/bin/env npx tsx
/**
 * Fetch a diverse sample of Swiss court decisions for seeding.
 * Pulls from different regions of the dataset to get varied courts/languages.
 *
 * Usage: npx -y tsx scripts/seed-diverse.ts
 */

const HF_API =
  'https://datasets-server.huggingface.co/rows?dataset=voilaj/swiss-caselaw&config=default&split=train';

interface Row {
  decision_id: string;
  court: string;
  canton: string;
  docket_number: string;
  decision_date: string;
  language: string;
  title: string;
  legal_area: string | null;
  regeste: string | null;
  full_text: string | null;
  cited_decisions: string | null;
  has_full_text: boolean;
}

async function fetchRows(offset: number, length: number): Promise<Row[]> {
  const response = await fetch(`${HF_API}&offset=${offset}&length=${length}`);
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  const data = await response.json();
  return data.rows.map((r: { row: Row }) => r.row);
}

function sanitizeId(id: string): string {
  return id.replace(/[^a-zA-Z0-9_]/g, '_').slice(0, 64);
}

function formatCourt(court: string): string {
  return court
    .split('_')
    .map((p, i) => (i === 0 ? p.toUpperCase() : p.charAt(0).toUpperCase() + p.slice(1)))
    .join(' ');
}

function transform(row: Row) {
  let citationsCount = 0;
  if (row.cited_decisions) {
    try { citationsCount = JSON.parse(row.cited_decisions).length; } catch {}
  }
  const pathParts: string[] = [];
  if (row.canton) pathParts.push(`Kanton ${row.canton}`);
  if (row.court) pathParts.push(formatCourt(row.court));
  if (row.legal_area) pathParts.push(row.legal_area);

  return {
    document_id: `doc_ocl_${sanitizeId(row.decision_id)}`,
    title: row.title || `${row.court} — ${row.docket_number}`,
    jurisdiction: 'CH',
    document_type: 'decision',
    language: row.language || 'de',
    effective_date: row.decision_date,
    structural_path: pathParts.length > 0 ? pathParts.join(' › ') : undefined,
    content: row.full_text ?? undefined,
    content_preview: (row.regeste ?? row.full_text ?? '').slice(0, 200) || undefined,
    sections_count: 0,
    citations_count: citationsCount,
    related_decisions_count: citationsCount,
    related_commentary_count: 0,
    source_id: 'src_opencaselaw',
    processed_at: new Date().toISOString(),
    court: row.court,
    docket_number: row.docket_number,
    regeste: row.regeste ?? undefined,
  };
}

async function main() {
  console.log('Fetching diverse sample from OpenCaseLaw...\n');

  // Sample from different offsets to get language + court diversity
  const batches = [
    { offset: 0, length: 5 },        // AG (German)
    { offset: 100000, length: 5 },    // another canton
    { offset: 200000, length: 5 },
    { offset: 300000, length: 5 },
    { offset: 500000, length: 5 },    // GE (French)
    { offset: 600000, length: 5 },
    { offset: 700000, length: 5 },    // likely federal
    { offset: 800000, length: 5 },
    { offset: 900000, length: 5 },
    { offset: 950000, length: 5 },
  ];

  const allRows: Row[] = [];
  for (const batch of batches) {
    try {
      const rows = await fetchRows(batch.offset, batch.length);
      allRows.push(...rows.filter((r) => r.has_full_text && r.full_text));
      console.log(
        `  offset ${batch.offset}: ${rows.length} rows (${rows[0]?.court} / ${rows[0]?.language})`,
      );
    } catch (err) {
      console.warn(`  offset ${batch.offset}: failed — ${err}`);
    }
  }

  // Deduplicate by decision_id
  const seen = new Set<string>();
  const unique = allRows.filter((r) => {
    if (seen.has(r.decision_id)) return false;
    seen.add(r.decision_id);
    return true;
  });

  const projections = unique.map(transform);

  // Write fixture
  const fs = await import('fs');
  const path = await import('path');
  const fixtureDir = path.join(import.meta.dirname ?? __dirname, '..', 'fixtures');
  fs.mkdirSync(fixtureDir, { recursive: true });
  const file = path.join(fixtureDir, 'seed-projections.json');
  fs.writeFileSync(file, JSON.stringify(projections, null, 2));

  // Stats
  const langs = new Map<string, number>();
  const courts = new Map<string, number>();
  const cantons = new Set<string>();
  for (const p of projections) {
    langs.set(p.language, (langs.get(p.language) ?? 0) + 1);
    if (p.court) courts.set(p.court, (courts.get(p.court) ?? 0) + 1);
    // extract canton from structural path
    const match = p.structural_path?.match(/Kanton (\w+)/);
    if (match) cantons.add(match[1]);
  }

  console.log(`\n═══ Results ═══`);
  console.log(`  Total:    ${projections.length} documents`);
  console.log(`  Languages: ${[...langs.entries()].map(([k, v]) => `${k}(${v})`).join(', ')}`);
  console.log(`  Cantons:   ${[...cantons].join(', ')}`);
  console.log(`  Courts:    ${courts.size} distinct courts`);
  console.log(`  w/ cites:  ${projections.filter((p) => p.citations_count > 0).length}`);
  console.log(`  Written:   ${file}`);
}

main().catch((err) => {
  console.error('Failed:', err);
  process.exit(1);
});
