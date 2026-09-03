// Provider conformance matrix — audit every registered acquisition provider against the things
// the repo asserts about it, and report only the ones where the assertion is false.
//
// WHY THIS EXISTS. `build_provider_registry` is thirteen `registry.register(...)` calls wrapped in
// ~50 lines of prose that states each provider's readiness, why it is that, and what would change
// it. NOTHING TESTS THAT PROSE. test_blueprint_provider_parity.py ties templates to
// `live_ready_names()`, and test_provider_enablement_lock.py pins the readiness semantics — but no
// test asserts that the comment above a `register()` call still describes the class below it.
// That drift is guarded socially, which is exactly how #833 happened: three registry comments
// outranked the code they described and had to be corrected by hand.
//
// It would also have caught #843 mechanically: four producers emit `in_force_until` and every one
// passes the upstream end-date through unadjusted, while `lexfind_api.is_in_force` treats the same
// date as EXCLUSIVE and the consumer (legal-search/api/src/core/norm-hierarchy/in-force.ts:24-27)
// defines it as INCLUSIVE. One provider's own tests document that as an inference, not a
// measurement. A per-provider sweep surfaces that as a row; reading one file does not.
//
// Reads only. Never registers, flips a readiness, edits a template, or contacts a provider's host.

export const meta = {
  name: 'provider-conformance-matrix',
  description:
    'Audit every acquisition provider against its own prose, its guards and its in_force_until reading; report only falsified claims',
  whenToUse:
    'After adding or promoting a provider, before a readiness change, or periodically — the registry comments are load-bearing and nothing tests them.',
  phases: [
    { title: 'Enumerate', detail: 'read the registry and split providers into audit batches' },
    { title: 'Audit', detail: 'one agent per batch, re-deriving each claim from the class' },
    { title: 'Refute', detail: 'an independent sceptic re-checks each batch\'s nonconformities' },
    { title: 'Matrix', detail: 'assemble the conformance table and the falsified-claim list' },
  ],
}

const A = args || {}
// Natural fan-out is 13 (one agent per provider) which, with a sceptic each plus the roster and
// matrix agents, is 28 — over the medium cap. Batching 3 providers per agent gives
// 5 audit + 5 refute + 2 = 12. Set providersPerAgent: 1 for the full 13-way fan-out (28 agents)
// when you want maximum independence.
const PER_AGENT = Math.max(1, A.providersPerAgent || 3)
// Restrict the sweep, e.g. args.only = ['lexfind_api', 'gemeinde_http'].
const ONLY = Array.isArray(A.only) ? A.only : null

const HOUSE = `
GROUND RULES (.claude/workflows/_house-rules.md):

1. NEVER TRUST A REPORTED RESULT. A comment, a docstring, an ADR, an issue body and this prompt
   itself are CLAIMS. Open the class and read the attribute. This workflow exists because the
   prose in this repo has repeatedly outranked the code it describes.

2. EVIDENCE OR SILENCE. Every row you emit is anchored to a quoted file:line or to the command
   that produced it. Report a claim ONLY when you have falsified it, or confirmed it by reading
   the code. Never report "looks fine" as a finding, and never report an improvement idea.

3. DID-NOT-RUN IS NOT PASS. If you run a test, use the CI-equivalent gate:
     bash scripts/check-platform-control.sh
   A bare \`uv run pytest\` is narrower than CI. And the script wraps its ENTIRE admin half in
   \`if [[ -f admin/package.json ]]\` (check-platform-control.sh:18) — if that file is absent the
   admin half is skipped SILENTLY and the script still exits 0, so read the output for the admin
   section rather than trusting the exit code. Missing platform-control/admin/node_modules is a
   DIFFERENT case and is NOT silent: :36-42 detects it, prints the exact \`npm ci\` remedy and exits
   non-zero.
   For a single test file, \`cd platform-control && uv run pytest tests/unit/<file> -x\` is fine, but
   say that is what you ran.

4. BOUNDARY. Do NOT merge a PR, push, delete a branch, or comment on a PR — this report is returned
   to the caller and a human acts on it. Do NOT contact any provider's upstream host — no curl, no fetch, no browser, in
   particular nothing at lexfind.ch, fedlex.admin.ch, entscheidsuche.ch, a cantonal or communal
   portal, or data.bka.gv.at. Do NOT dispatch a run in any mode. Do NOT change a provider's
   \`readiness\` or a template's \`enabled\` key: those are the two keys of the ADR-0030 lock and
   neither is an agent's to turn. If a check can only be settled by a live call, emit it as
   NEEDS-HUMAN-DECISION with the exact call a human would make.

5. LEAVE THE TREE CLEAN. If you mutate a file to test whether anything notices, revert it
   (git checkout -- <path>) and say so explicitly in your answer.
`

// The checks. Each is grounded in a defect this repo actually shipped.
const CHECKS = `
For EACH provider assigned to you, answer all six. Cite file:line for every answer.

C1 — REGISTRY PROSE vs CLASS ATTRIBUTE.
    Read the comment block above this provider's \`registry.register(...)\` call in
    platform-control/src/platform_control/services/provider_registry_factory.py. Extract every
    factual claim it makes (the readiness value, whether start_run is real, why it is shut, what
    evidence exists, which issue). Then open the class and check each claim against the code.
    Report a row ONLY where the prose is FALSE or the citation has rotted.
    Precedent: #833 — three registry comments described a state the classes no longer had.

C2 — MODULE PROSE vs CLASS ATTRIBUTE.
    Same check against the provider module's own header docstring and its class docstring.
    \`live_ready: bool\` is DEPRECATED but NOT GONE — provider_readiness() still honours it as a
    fallback at src/acquisition_core/providers.py:175. So a comment saying live_ready is "gone" is
    false, and a comment instructing someone to "set live_ready = True" is a no-op because
    \`readiness\` wins. Both shapes have been on main. Verify against
    src/acquisition_core/providers.py:159-177 (provider_readiness), NOT against my description of it.

C3 — READINESS DECLARED AND FAIL-CLOSED.
    Does the class declare \`readiness\` explicitly? If it inherits from
    portal_http_provider_base.py, does it override or re-state it? A provider declaring neither
    \`readiness\` nor \`live_ready\` resolves to SCAFFOLD (providers.py:177) — fail-closed by design.
    Confirm the resolved value by reading provider_readiness(), not by reading a comment.

C4 — CAPTURE-GUARD USAGE.
    First, DERIVE the guard set: open src/acquisition_core/artifact_guard.py and list every falsy
    branch \`check_capture\` can return, with its reason string. Do NOT assume a count — issue #731's
    prose and the implementation do not agree on how many there are, and at least one check named in
    that issue (an extracted-character / text-marker floor) is delegated elsewhere rather than
    implemented in the guard.
    Then, for this provider: does it call check_capture at all? With what min_bytes? Are refusals
    RECORDED with a reason and detail (the lexfind_api path appends to skipped[] with reason+detail),
    or silently dropped? A dropped refusal is the finding — it reads as "nothing was refused".
    If the provider does not fetch binaries, say so and mark N/A rather than inventing a gap.

C5 — in_force_until READING.
    Does this provider emit \`in_force_until\` (or an equivalent end-date)? From which upstream
    field? Does it ADJUST the date (e.g. subtract a day) or pass it through? And — the part that
    matters — does it DOCUMENT whether it reads the date as INCLUSIVE (last day still in force) or
    EXCLUSIVE (first day no longer in force)?
    Cross-check the consumer: legal-search/api/src/core/norm-hierarchy/in-force.ts. Whatever it
    says there is the contract. A producer that ships an unadjusted upstream date without stating
    its reading is a finding even when the date happens to be right, because the next producer
    copies it. Precedent: #843.

C6 — WOULD A TEST NOTICE?
    Mutation check on the readiness key. Change this provider's \`readiness\` to a different value
    (e.g. LIVE -> SCAFFOLD, or delete the attribute entirely), run the narrowest platform-control
    unit selection, and record whether anything goes red. THEN REVERT (git checkout -- <path>) and
    say you did.
    A readiness that nothing pins is a config key with no guard. Note which test caught it, if any.
`

const AUDIT_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['rows'],
  properties: {
    rows: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['provider', 'readiness_resolved', 'checks'],
        properties: {
          provider: { type: 'string' },
          readiness_resolved: { type: 'string', description: 'As resolved by provider_readiness(), with file:line.' },
          checks: {
            type: 'array',
            items: {
              type: 'object',
              additionalProperties: false,
              required: ['check', 'status'],
              properties: {
                check: { type: 'string', enum: ['C1', 'C2', 'C3', 'C4', 'C5', 'C6'] },
                status: {
                  type: 'string',
                  enum: ['CONFORMS', 'FALSIFIED', 'NOT_APPLICABLE', 'NEEDS_HUMAN_DECISION', 'COULD_NOT_CHECK'],
                },
                anchor: { type: 'string', description: 'file:line, quoted.' },
                detail: { type: 'string', description: 'What the prose claims and what the code does.' },
                fix: { type: 'string' },
              },
            },
          },
          reverted_mutations: { type: 'string', description: 'What you changed and confirmed reverted.' },
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
        required: ['provider', 'check', 'refuted', 'reason'],
        properties: {
          provider: { type: 'string' },
          check: { type: 'string' },
          refuted: { type: 'boolean' },
          reason: { type: 'string' },
          corrected_anchor: { type: 'string' },
        },
      },
    },
  },
}

// ── run ──────────────────────────────────────────────────────────────────────
phase('Enumerate')

const roster = await agent(
  `${HOUSE}

Read platform-control/src/platform_control/services/provider_registry_factory.py and return, as a
JSON array and nothing else, one entry per provider that \`build_provider_registry\` registers:

  {"key": "<provider_name string>", "class": "<ClassName>", "module": "<path>",
   "register_line": "provider_registry_factory.py:<line>",
   "readiness_line": "<module>.py:<line>", "readiness_value": "<LIVE|SCAFFOLD|AWAITING_EVIDENCE|none declared>"}

Read the registration order from the code — do not rely on the import list, which is alphabetical
and does not match registration order. If a provider declares no \`readiness\`, say
"none declared" and do not guess what it resolves to; C3 handles that.
Return ONLY the JSON array.`,
  { label: 'read the registry' },
)

let providers = []
try {
  const m = String(roster).match(/\[[\s\S]*\]/)
  providers = m ? JSON.parse(m[0]) : []
} catch (e) {
  providers = []
}
if (providers.length === 0) {
  log('⚠ could not parse the registry roster — falling back to the registration order on main')
  providers = [
    'firecrawl', 'deterministic_http', 'fedlex_sparql', 'ris_ogd', 'eur_lex_sparql',
    'legifrance', 'bundesland_http', 'regione_http', 'ch_court_decisions', 'canton_http',
    'lexfind_api', 'gemeinde_http', 'cassette',
  ].map((key) => ({ key }))
}
if (ONLY) {
  const before = providers.length
  providers = providers.filter((p) => ONLY.indexOf(p.key) !== -1)
  log(`args.only restricted the sweep to ${providers.length} of ${before} providers`)
}
// Backstop against a bogus roster: the registry has 13 providers, so anything past 20 is a parse
// artefact, and batching it would spawn dozens of agents.
const ROSTER_CEILING = 20
if (providers.length > ROSTER_CEILING) {
  log(`⚠ roster returned ${providers.length} providers, which is not plausible for this registry; capped to ${ROSTER_CEILING}. The remainder was NOT AUDITED.`)
  providers = providers.slice(0, ROSTER_CEILING)
}

const batches = []
for (let i = 0; i < providers.length; i += PER_AGENT) {
  batches.push(providers.slice(i, i + PER_AGENT))
}
log(`${providers.length} providers → ${batches.length} batch(es) of ≤${PER_AGENT}; ~${batches.length * 2 + 2} agents`)

const results = await pipeline(
  batches,

  // Stage 1 — audit this batch.
  (batch, _orig, idx) =>
    agent(
      `${HOUSE}

You are auditing acquisition providers ${batch.map((p) => p.key).join(', ')} (batch ${idx + 1} of ${batches.length}).

REGISTRY ROSTER as read by another agent — a starting map, NOT fact. Re-open every file you rely on:
${JSON.stringify(batch, null, 2)}

${CHECKS}

Emit one row per provider with one entry per check C1..C6. Use CONFORMS when you checked and the
claim holds — that is a real result and the matrix needs it. Use FALSIFIED only when you can quote
the prose and quote the contradicting code. Use COULD_NOT_CHECK rather than guessing.`,
      { phase: 'Audit', label: `audit ${batch.map((p) => p.key).join('+')}`, schema: AUDIT_SCHEMA },
    ),

  // Stage 2 — refute this batch's nonconformities, as soon as the batch reports.
  async (audit, batch, idx) => {
    if (!audit) return null
    const bad = []
    ;(audit.rows || []).forEach((r) =>
      (r.checks || []).forEach((c) => {
        if (c.status === 'FALSIFIED' || c.status === 'NEEDS_HUMAN_DECISION') {
          bad.push({ provider: r.provider, check: c.check, anchor: c.anchor, detail: c.detail })
        }
      }),
    )
    if (bad.length === 0) return { audit, verdicts: [] }

    const panel = await agent(
      `${HOUSE}

You are the sceptic for batch ${idx + 1} (${batch.map((p) => p.key).join(', ')}).
YOUR JOB IS TO KILL THESE CLAIMED NONCONFORMITIES, not to confirm them.

${JSON.stringify(bad, null, 2)}

For each: open the cited file at the cited line yourself. Does the line say what is claimed? Is the
line number still correct? Does the code genuinely contradict the prose, or is the auditor reading
a deprecated-but-honoured fallback as if it were dead (live_ready is deprecated and STILL honoured
at src/acquisition_core/providers.py:175 — mistaking that for a contradiction is the likeliest
false positive here)?

refuted = true unless you personally re-derived it. Default to refuted when uncertain.
If the anchor is right but the line number moved, set corrected_anchor.`,
      { phase: 'Refute', label: `refute batch ${idx + 1}`, schema: REFUTE_SCHEMA },
    )
    return { audit, verdicts: (panel && panel.verdicts) || [] }
  },
)

const ok = results.filter(Boolean)
const lost = batches.length - ok.length
if (lost > 0) log(`⚠ ${lost} batch(es) produced no result — those providers are UNAUDITED, not clean`)

// Fold the refutations back into the rows.
const rows = []
let refutedCount = 0
ok.forEach((r) => {
  ;(r.audit.rows || []).forEach((row) => {
    const checks = (row.checks || []).map((c) => {
      const v = r.verdicts.find((x) => x.provider === row.provider && x.check === c.check)
      if (!v) return c
      if (v.refuted) {
        refutedCount++
        return { ...c, status: 'REFUTED', detail: `${c.detail} — REFUTED: ${v.reason}` }
      }
      return { ...c, anchor: v.corrected_anchor || c.anchor, detail: `${c.detail} — confirmed: ${v.reason}` }
    })
    rows.push({ ...row, checks })
  })
})

const survived = rows.flatMap((r) =>
  (r.checks || [])
    .filter((c) => c.status === 'FALSIFIED' || c.status === 'NEEDS_HUMAN_DECISION')
    .map((c) => ({ provider: r.provider, ...c })),
)
log(`${rows.length} providers audited; ${survived.length} nonconformities survived, ${refutedCount} refuted`)

phase('Matrix')
const report = await agent(
  `${HOUSE}

Assemble the provider conformance report.

AUDITED ROWS (refutations already folded in; anything marked REFUTED was killed by an independent
sceptic and must NOT reappear as a finding):
${JSON.stringify(rows, null, 2)}

SURVIVING NONCONFORMITIES:
${JSON.stringify(survived, null, 2)}

UNAUDITED BATCHES: ${lost}

Write exactly this, and nothing else:

1. MATRIX — a markdown table, one row per provider, columns:
   provider | resolved readiness | C1 prose | C2 module prose | C3 readiness | C4 capture guard |
   C5 in_force_until | C6 pinned by a test?
   Cell values: OK / FALSIFIED / N/A / NEEDS-HUMAN / UNCHECKED. Nothing else in the cells.

2. FALSIFIED CLAIMS — numbered, worst first. Each: the provider, the prose quoted verbatim, the
   contradicting code quoted with file:line, and the one-line fix. If the fix is a comment edit,
   say so — a stale comment is a real defect in this repo (#833) and the fix is cheap.

3. UNPINNED READINESS — every provider where C6 found that changing \`readiness\` turned nothing
   red. Name the missing test.

4. in_force_until LEDGER — one line per producer: upstream field, adjusted or passthrough,
   documented reading (inclusive / exclusive / UNSTATED), agrees with
   legal-search/api/src/core/norm-hierarchy/in-force.ts yes/no. UNSTATED is a finding.

5. NOT ESTABLISHED — unaudited batches, COULD_NOT_CHECK cells, and every NEEDS-HUMAN-DECISION with
   the exact call a human would have to make. Do not round this section up to "all clear".

Terse. No preamble, no emoji. Do not open a PR, do not edit any file, do not change any readiness
or \`enabled\` key — this report is returned to the caller and a human decides.`,
  { label: 'conformance matrix' },
)

return report
