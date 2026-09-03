// Claims vs enforcement — for every invariant this repo asserts in prose, find the code that
// enforces it and the test that would fail if that enforcement were deleted. Report only the
// invariants where one of those does not exist.
//
// WHY THIS SEAM IS THE RICHEST ONE HERE. This repo writes unusually good comments: ADRs with
// numbered guarantees, module headers that explain why a key is shut, docstrings that say what
// must never happen. That prose is load-bearing — people and agents act on it. And prose has no
// build step. Four shapes of this defect have surfaced:
//
//   - An issue's "non-negotiable" multi-part guard shipped with parts of it delegated elsewhere or
//     absent, while the prose still read as if all of it were implemented (#731 / artifact_guard.py).
//   - An ADR claimed CI enforcement that was real but coarser than the claim (bucket-granular,
//     not per-item) — enforcement existed, at the wrong granularity, which is harder to see than
//     no enforcement at all (ADR-0049).
//   - An ADR specified a per-source override lever that nothing produces (ADR-0047).
//   - A comment said `live_ready` was "gone" when provider_readiness still honours it as a
//     fallback at src/acquisition_core/providers.py:175.
//
// THE FAILURE MODE THIS SCRIPT IS BUILT AGAINST is an agent that reads an ADR and writes "this
// could be better enforced". That is a wishlist item. The output here is: invariant, quoted; the
// enforcement, at file:line, or NONE; the test that would fail, at file:line, or NONE.
//
// Read-only. It NAMES the test that should fail; it does not break code to prove it. That proof is
// guard-efficacy-mutation.js, which does the same thing by mutation inside a throwaway worktree.

export const meta = {
  name: 'claims-vs-enforcement',
  description:
    'Find invariants asserted in ADRs, AGENTS.md, docstrings and comments that no code enforces or no test would notice losing',
  whenToUse:
    'Periodically, or before trusting an ADR guarantee in new work. Answers "which of our stated rules are actually load-bearing?" — the answer is never all of them.',
  phases: [
    { title: 'Harvest', detail: 'enumerate the documents that assert invariants and batch them' },
    { title: 'Trace', detail: 'per batch: extract each invariant, locate its enforcement and its test' },
    { title: 'Refute', detail: 'an independent sceptic hunts for the enforcement the tracer missed' },
    { title: 'Rank', detail: 'top findings by blast radius; unenforced beats under-enforced' },
  ],
}

const A = args || {}
// Batches of invariant-bearing documents. Default 6 keeps a full run at 14 agents.
const BATCHES = Math.max(1, Math.min(8, A.batches || 6))
// Restrict the harvest, e.g. args.scope = 'docs/adr' or 'platform-control/src'.
const SCOPE = A.scope || null
const TOP_N = A.topN || 10

const HOUSE = `
GROUND RULES (.claude/workflows/_house-rules.md):

1. EVIDENCE OR SILENCE. Every finding has three anchors and is dropped without them:
     (a) the INVARIANT, quoted verbatim, with file:line;
     (b) the ENFORCEMENT, at file:line — or the word NONE, after you searched;
     (c) the TEST that would fail if the enforcement were deleted, at file:line — or NONE.
   "This could be better enforced", "consider adding a test", "this seems fragile" are not
   findings. They are dropped by construction. An empty report from a search that actually ran is
   a real and useful result; a wishlist is worse than nothing.

2. SEARCH BEFORE YOU DECLARE NONE. The enforcement is often not next to the claim. Look for: a
   runtime assertion or raise; a Pydantic/DTO validator; a unit test; a CI step in
   .github/workflows/; a script under scripts/check-*.sh or scripts/check_*.py; a pre-commit hook
   in .pre-commit-config.yaml; a lint rule in biome.json / ruff config; a type that makes the state
   unrepresentable. Grep for the distinctive nouns of the invariant, not for its wording.

3. UNDER-ENFORCEMENT IS A DISTINCT AND HARDER FINDING. Enforcement that exists at the wrong
   granularity is worse than none, because the claim reads as covered. Precedent: a CI gate that
   checked a bucket when the ADR guaranteed a per-item property. When you find enforcement, ask
   whether it is as strong as the sentence says — same scope, same granularity, same direction —
   and quote both so a reader can compare.

4. NEVER TRUST PROSE, INCLUDING THIS PROMPT. An ADR marked Accepted may describe a system that was
   never built. A comment may describe code that has since changed. Open the code.

5. READ-ONLY. Do not edit, mutate, or revert anything. Do not run a gate that regenerates a
   tracked artifact. If proving a finding requires breaking code, do not — record it as
   "unproven: needs mutation" and name the exact mutation. guard-efficacy-mutation.js does that
   part, inside its own worktree.

6. BOUNDARY. No public-sector host, no acquisition run, no config-key flip, no merge, no push, no
   PR comment.
`

const WHERE = `
WHERE INVARIANTS ARE ASSERTED IN THIS REPO (harvest from these; the list is a starting point, not
a boundary — say if you find another seam):
  docs/adr/*.md              — numbered decisions. Look for MUST / MUST NOT / never / always /
                               "is enforced by" / "the build fails if" / "guaranteed". An ADR that
                               says a gate exists is asserting a testable fact about CI.
  AGENTS.md, CLAUDE.md       — repo-wide rules, the per-surface gate table, the source-of-truth
                               hierarchy, the serialization rules. Each row is an invariant.
  docs/architecture/*.md     — narrative claims about boundaries and what is / is not built.
  docs/runbooks/*.md         — operator guarantees.
  module and class docstrings, and block comments above a registry or a config table — this repo
                               puts load-bearing rationale there (e.g. why a key is shut, why a
                               provider is at a given readiness, why a fallback exists).
  contracts/                 — a schema is an enforced invariant; check the enforcement is wired.
`

const TRACE_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['findings', 'coverage'],
  properties: {
    coverage: {
      type: 'string',
      description: 'Which documents you actually read, and how many invariants you extracted from each.',
    },
    findings: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['invariant', 'invariant_anchor', 'verdict', 'enforcement', 'test'],
        properties: {
          invariant: { type: 'string', description: 'Quoted verbatim from the source.' },
          invariant_anchor: { type: 'string', description: 'file:line' },
          verdict: {
            type: 'string',
            enum: ['UNENFORCED', 'UNDER_ENFORCED', 'ENFORCED_BUT_UNTESTED', 'FALSE_CLAIM'],
          },
          enforcement: { type: 'string', description: 'file:line of the enforcing code, or NONE (after searching).' },
          test: { type: 'string', description: 'file:line of the test that would fail, or NONE.' },
          searched: { type: 'string', description: 'The greps and paths you searched before writing NONE.' },
          gap: { type: 'string', description: 'For UNDER_ENFORCED: what the claim says vs what the check does.' },
          blast_radius: { type: 'string', enum: ['ship-blocker', 'high', 'medium', 'low'] },
          fix: { type: 'string', description: 'The narrowest change: a test, a gate line, or a corrected sentence.' },
        },
      },
    },
  },
}

const REFUTE_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['verdicts'],
  properties: {
    verdicts: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['invariant_anchor', 'refuted', 'reason'],
        properties: {
          invariant_anchor: { type: 'string' },
          refuted: { type: 'boolean' },
          reason: { type: 'string' },
          enforcement_found: { type: 'string', description: 'file:line of enforcement the tracer missed.' },
          severity_after_check: { type: 'string', enum: ['ship-blocker', 'high', 'medium', 'low', 'none'] },
        },
      },
    },
  },
}

const SEVERITY = ['ship-blocker', 'high', 'medium', 'low', 'none']
// Sort key for blast radius. `indexOf` returns -1 for a missing or unrecognised value, which
// would sort an unlabelled finding ABOVE a ship-blocker; 99 puts it last instead.
const rank = (s) => (SEVERITY.indexOf(s) + 1 || 99)

// ── run ──────────────────────────────────────────────────────────────────────
phase('Harvest')

const harvest = await agent(
  `${HOUSE}
${WHERE}

Do NOT trace anything yet. Build the work list.
${SCOPE ? `Restrict the harvest to: ${SCOPE}\n` : ''}
1. List the candidate documents, with a one-line note on how invariant-dense each looks. Prefer
   documents that make CHECKABLE assertions (a gate exists, a field is always present, a key is
   never inherited) over ones that state intent.
2. Prioritise: an ADR marked Accepted that describes enforcement outranks a narrative doc; a
   comment above a registry or a config table outranks a general design note. Recently changed
   documents outrank old stable ones only if the code around them also changed
   (\`git log --oneline -20 -- docs/adr/\` and equivalent).
3. Split them into exactly ${BATCHES} balanced batches. Balance by expected invariant COUNT, not by
   file count — AGENTS.md alone is denser than several ADRs.
4. Note any seam my list missed.

Return ONLY a JSON object:
  {"batches": [["<path>", ...], ...], "notes": "...", "extra_seams": ["..."]}
with exactly ${BATCHES} batches.`,
  { label: 'harvest invariant sources' },
)

let batches = []
try {
  const m = String(harvest).match(/\{[\s\S]*\}/)
  const parsed = m ? JSON.parse(m[0]) : null
  if (parsed && Array.isArray(parsed.batches)) {
    // Cap: BATCHES is asked for in the prompt, not enforced by it. A model-controlled fan-out is
    // not a fan-out budget.
    batches = parsed.batches.filter((b) => b && b.length).slice(0, BATCHES)
    if (parsed.batches.length > batches.length) {
      log(`⚠ harvest returned ${parsed.batches.length} batches; capped to ${BATCHES}. The remainder was NOT SWEPT.`)
    }
  }
} catch (e) {
  batches = []
}
if (batches.length === 0) {
  log('⚠ could not parse the harvest — falling back to a fixed split. Coverage will be uneven.')
  batches = [
    ['docs/adr/ (first third, by number)'],
    ['docs/adr/ (second third, by number)'],
    ['docs/adr/ (final third, by number)'],
    ['AGENTS.md', 'CLAUDE.md'],
    ['docs/architecture/'],
    ['platform-control/src/ module and class docstrings, registry comment blocks'],
  ].slice(0, BATCHES)
}
log(`${batches.length} batch(es); ~${batches.length * 2 + 2} agents`)

const results = await pipeline(
  batches,

  (batch, _o, idx) =>
    agent(
      `${HOUSE}

Trace invariants to their enforcement. Batch ${idx + 1} of ${batches.length}:
${JSON.stringify(batch, null, 2)}

METHOD, in order:
  1. Read each document. Extract every CHECKABLE invariant — a sentence that could be shown false
     by running something. Skip intent, rationale and history; they are not invariants.
  2. For each, find the enforcement. Search properly (ground rule 2) before writing NONE, and
     record the searches you ran in \`searched\` — a NONE with no search behind it is worthless.
  3. For each enforcement, find the test that would go red if it were deleted. Name it at
     file:line. If the enforcement is a CI step or a check script, the "test" is that step — say
     which workflow file and which line invokes it, and whether it runs on every PR or only on a
     path filter. A gate that a path filter excludes for the very change it guards is UNDER_ENFORCED.
  4. Classify:
       UNENFORCED            — the invariant is asserted and nothing checks it.
       UNDER_ENFORCED        — something checks a weaker property than the sentence claims. Fill in
                               \`gap\` with both, quoted, so a reader can compare.
       ENFORCED_BUT_UNTESTED — the check exists but nothing would notice if it were deleted.
       FALSE_CLAIM           — the code contradicts the sentence outright.
  5. Report ONLY these four. An invariant that is enforced and tested is not a finding; count it in
     \`coverage\` and move on.

Rank your own findings by blast radius: what breaks in production, or what a future agent would do
wrong having believed the sentence. An unenforced rule that everybody follows anyway is low.`,
      { phase: 'Trace', label: `trace batch ${idx + 1}`, schema: TRACE_SCHEMA },
    ),

  async (traced, batch, idx) => {
    if (!traced || !traced.findings || traced.findings.length === 0) {
      return { survivors: [], killed: 0, coverage: (traced && traced.coverage) || 'no coverage reported' }
    }
    const panel = await agent(
      `${HOUSE}

You are the sceptic for batch ${idx + 1}. YOUR JOB IS TO FIND THE ENFORCEMENT THE TRACER MISSED.

Claimed findings:
${JSON.stringify(traced.findings, null, 2)}

For each one:
  - Search for the enforcement YOURSELF, and search differently from the tracer: grep the
    invariant's distinctive nouns across .github/workflows/, .pre-commit-config.yaml, scripts/,
    biome.json, ruff settings in pyproject.toml, conftest.py, and any *_test / test_* file whose
    name contains a related word. Check whether a TYPE makes the bad state unrepresentable — that
    is enforcement too, and it is the one tracers miss most.
  - Open the invariant's own anchor and confirm the quote is accurate and the line number current.
  - For UNDER_ENFORCED: is the gap real, or is the tracer comparing a summary sentence against a
    precise check? Prose is usually looser than code; that alone is not a finding.
  - For a FALSE_CLAIM about a deprecated mechanism: is the mechanism actually dead, or deprecated
    and still honoured? Those are different, and confusing them is the likeliest false positive
    here (precedent: live_ready is deprecated AND still honoured at
    src/acquisition_core/providers.py:175).

refuted = true unless you personally failed to find enforcement after searching. Default to
refuted = true when uncertain — absence of proof is refutation. If you found enforcement, put it in
enforcement_found so the finding is not merely killed but corrected.`,
      { phase: 'Refute', label: `refute batch ${idx + 1}`, schema: REFUTE_SCHEMA },
    )
    const verdicts = (panel && panel.verdicts) || []
    const survivors = []
    let killed = 0
    traced.findings.forEach((f) => {
      const v = verdicts.find((x) => x.invariant_anchor === f.invariant_anchor)
      if (!v) {
        survivors.push({ ...f, status: 'UNVERIFIED — no sceptic verdict' })
        return
      }
      if (v.refuted) {
        killed++
        return
      }
      survivors.push({
        ...f,
        status: 'SURVIVED',
        blast_radius: v.severity_after_check && v.severity_after_check !== 'none' ? v.severity_after_check : f.blast_radius,
        sceptic_note: v.reason,
      })
    })
    log(`batch ${idx + 1}: ${survivors.length} survived, ${killed} refuted`)
    return { survivors, killed, coverage: traced.coverage }
  },
)

const ok = results.filter(Boolean)
const lost = batches.length - ok.length
if (lost > 0) log(`⚠ ${lost} batch(es) produced nothing — those documents are UNSWEPT, not clean`)

const all = ok.flatMap((r) => r.survivors)
const ORDER = { UNENFORCED: 0, FALSE_CLAIM: 1, UNDER_ENFORCED: 2, ENFORCED_BUT_UNTESTED: 3 }
all.sort((a, b) => {
  const s = rank(a.blast_radius) - rank(b.blast_radius)
  return s !== 0 ? s : (ORDER[a.verdict] || 9) - (ORDER[b.verdict] || 9)
})
const top = all.slice(0, TOP_N)
if (all.length > top.length) log(`capped at ${TOP_N}: dropped ${all.length - top.length} lower-blast-radius findings`)

phase('Rank')
const report = await agent(
  `${HOUSE}

Write the claims-vs-enforcement report.

SURVIVING FINDINGS (each already survived an independent sceptic who searched for the enforcement;
${all.length} survived, ${ok.reduce((n, r) => n + r.killed, 0)} were refuted and must not reappear):
${JSON.stringify(top, null, 2)}

COVERAGE, as reported per batch:
${ok.map((r, i) => `  batch ${i + 1}: ${r.coverage}`).join('\n')}

BATCHES THAT PRODUCED NOTHING: ${lost}

Write exactly this and nothing else:

1. HEADLINE — one line: how many invariants were traced, how many are unenforced, how many
   under-enforced. Numbers only; no adjectives.

2. FINDINGS — numbered, worst first. Each entry, in four lines and no more:
     CLAIM:       "<verbatim quote>" — <file:line>
     ENFORCEMENT: <file:line> | NONE (searched: <what was searched>)
     WOULD FAIL:  <test file:line> | NONE
     FIX:         <the narrowest change — a test, one CI line, or a corrected sentence>
   For UNDER_ENFORCED, add one line: GAP: <what the claim says> vs <what the check does>.

3. UNPROVEN — findings whose confirmation needs a mutation this workflow will not perform. For
   each, give the exact mutation and the exact gate, so guard-efficacy-mutation.js can be pointed
   straight at it.

4. NOT SWEPT — unswept batches and documents nobody read. Do not round this up to "the repo is
   consistent"; this workflow read a sample.

Terse. No preamble, no emoji, no praise. Every line must carry a file:line or a number. If a
finding cannot be stated with an anchor, delete it rather than softening it.
Do not edit any file and do not open a PR.`,
  { label: 'enforcement report' },
)

return report
