// Cantonal onboarding — DRY RUN. Drafts and validates blueprint templates for the Swiss cantons
// that do not have one, and produces a decision memo. It never fetches, never dispatches a run,
// and never flips a key.
//
// ── READ THIS BEFORE CHANGING THE FAN-OUT AXIS ───────────────────────────────
// A measurement doing the rounds says 19 of 22 cantonal portals serve a byte-identical robots.txt
// (~86% on one platform), and concludes that per-canton onboarding is therefore an N-way fan-out
// over CANTONAL PORTALS. That conclusion points at the `canton_http` provider, and this repo says
// not to plan against it:
//
//   docs/architecture/ch-acquisition-coverage-status.md — "Cantonal portal scraping (canton_http)
//   | scaffold | Superseded by LexFind. Do not plan against it"
//
//   canton_http_provider.py:48 — readiness = SCAFFOLD, because the ZH-Lex-style SPA portals never
//   serve the statute to a deterministic fetch (#631/#716): the erlass page is metadata-only and
//   its only text link points at a host that refuses TCP.
//
// A shared robots.txt tells you the portals share a CMS. It does not tell you the statute text is
// reachable, and #716 measured that it is not. So the fan-out axis here is NOT portals. It is
// roadmap step 8 of that same document: "Remaining 23 cantons — Per-canton templates; the provider
// is unchanged, the cost is config + evidence", against `lexfind_api` (readiness = LIVE since
// #815, one unauthenticated JSON API covering 26 cantons + Bund).
//
// That makes this workflow pure config authoring plus validation against repo-local reference
// data — which is exactly why it can be honest about needing no network at all.
//
// ── THE BOUNDARY THIS WORKFLOW STOPS AT ──────────────────────────────────────
// Three things are NOT ours to decide, and the memo is where each one lands:
//   1. LexFind's terms were never confirmed with the Schweizerische Staatsschreiberkonferenz. No
//      agent contacts lexfind.ch.
//   2. `entity_ids` is the one field that cannot be derived from this repo for most cantons. Only
//      ZH=26, BE=4 and BS=6 are pinned by committed evidence. The rest require a live
//      `entities/extended` call — a human decides whether to make it.
//   3. `enabled: true` is the operator's key under ADR-0030, turned against captured acceptance
//      evidence. Every template this workflow drafts ships `enabled: false`, and the workflow
//      cannot turn it.

export const meta = {
  name: 'cantonal-onboarding-dry-run',
  description:
    'Draft and validate lexfind_api blueprint templates for cantons that have none, and emit a decision memo — no fetch, no run, no key flip',
  whenToUse:
    'Planning the cost of the Nth cantonal source (roadmap step 8). Produces reviewable YAML and a blocker list; an operator still authors, runs and enables.',
  phases: [
    { title: 'Ground', detail: 'read the committed templates, reference seeds and evidence bundles' },
    { title: 'Draft', detail: 'one agent per canton batch, drafting and self-validating templates' },
    { title: 'Refute', detail: 'an independent sceptic attacks each batch\'s drafts and blockers' },
    { title: 'Memo', detail: 'decision memo — what a human must approve, and what is still unknown' },
  ],
}

const A = args || {}
// 23 cantons without a template. One agent each (plus a sceptic) is 48 agents — far over the cap.
// 4 per agent gives 6 draft + 6 refute + 2 = 14. Set cantonsPerAgent: 1 for maximum independence
// (48 agents), or pass args.cantons to scope the run to a handful.
const PER_AGENT = Math.max(1, A.cantonsPerAgent || 4)
const ONLY = Array.isArray(A.cantons) ? A.cantons.map((c) => String(c).toLowerCase()) : null

const HOUSE = `
GROUND RULES (.claude/workflows/_house-rules.md) — the first one is not negotiable:

1. NO NETWORK, AT ALL, TO ANY SOURCE HOST. Do NOT curl, fetch, browse or otherwise contact
   lexfind.ch, any cantonal portal (zh.ch, be.ch, bs.ch, ...), fedlex.admin.ch, entscheidsuche.ch
   or any other public-sector host. LexFind's terms were never confirmed with the Schweizerische
   Staatsschreiberkonferenz. Everything you need is in this repository. If a fact is only
   obtainable from a live call, that fact is a BLOCKER for the memo, not a task for you.

2. DO NOT DISPATCH A RUN in any mode (live, acceptance, shadow, dry). Not via the API, not via a
   fast-loop script in scripts/, not via the evidara CLI.

3. DO NOT FLIP A KEY. Every template you draft carries \`enabled: false\`. That key is the
   operator's under ADR-0030 and is turned against captured acceptance evidence, never inherited
   and never set by an agent. Do not change any provider's \`readiness\` either.

4. WRITE NOTHING INTO THE REPO. Do not edit source_blueprints.yaml, do not add seed rows, do not
   create files. Your YAML goes in your ANSWER, as text, for a human to review and paste. If you
   ran anything that touched the tree, revert it and say so.

5. EVIDENCE OR SILENCE. Every field you propose is either copied from a committed template, read
   from a committed seed file, or marked UNKNOWN with the exact source a human would need. Do not
   invent an entity id, a systematic number, a corpus id or a language. An invented entity id
   produces a template that runs against the wrong canton and looks like it worked.

6. NEVER TRUST PROSE. Comments, ADRs, issue bodies and this prompt are claims. Open the YAML and
   the seed files and read them.
`

const REFERENCE = `
WHERE THE GROUND TRUTH LIVES (open these; do not rely on my summary):
  platform-control/src/platform_control/hierarchies/source_blueprints.yaml
      — every blueprint template. The lexfind_api ones (lexfind_api_zh_tierschutz,
        lexfind_api_be_hunde, lexfind_api_bs_hunde, lexfind_api_zh_full) are your shape reference.
  platform-control/src/platform_control/seeds/reference/jurisdictions.yaml
      — canonical jurisdiction ids. All 26 cantons are already seeded as jur_ch_<xx>.
  platform-control/src/platform_control/seeds/reference/extractor_profiles.yaml
      — extractor_profile_id must exist here; tests/unit/test_blueprint_provider_parity.py:183
        pins that.
  platform-control/src/platform_control/seeds/reference/compliance_policies.yaml
      — the per-jurisdiction politeness/retention tiers.
  platform-control/src/platform_control/services/lexfind_api_provider.py
      — the acquisition spec this provider actually reads, the search contract, and what happens
        when entity_ids is absent.
  platform-control/tests/unit/test_blueprint_provider_parity.py
      — what a template must satisfy to be valid at all.
  docs/architecture/ch-acquisition-coverage-status.md
      — the roadmap this work sits in, and what is explicitly NOT BUILT.
  docs/runbooks/evidence/
      — the committed acceptance bundles. These, and only these, are evidence.
`

const CHECKS = `
For EACH canton assigned to you, produce a draft template and run all eight validations.
Cite file:line for every answer. A validation you could not perform is UNKNOWN, never OK.

V1 JURISDICTION — does jur_ch_<xx> exist in seeds/reference/jurisdictions.yaml? Quote the line.

V2 ENTITY ID — this is the hard one and the honest answer is usually "blocked".
   \`entity_ids\` scopes a LexFind query to one canton. Getting it wrong silently returns another
   canton's law. Only three are pinned by committed evidence in this repo: ZH=26, BE=4, BS=6
   (source_blueprints.yaml, in the lexfind templates' inline comments). Search the whole repo —
   templates, provider comments, tests, docs/runbooks/evidence/ — for any other canton's entity id.
   If you cannot find one committed here, the value is UNKNOWN and this canton is BLOCKED. Say so.
   Do NOT infer it from alphabetical order, canton abbreviation order, BFS number, or the three
   known values. There is no evidence the mapping is ordered, and a wrong id is worse than none.
   The only way to learn it is the provider's \`entities/extended\` call, which is a HUMAN DECISION.

V3 CORPUS — what corpus_id would this template write into? Follow the convention the committed
   templates use (corpus_public_ch_canton_<xx>_legislation). Then check whether that corpus is
   referenced anywhere else in the repo, and say plainly whether creating it is a separate act a
   human must perform, or whether templates create corpora implicitly. Read the code; do not guess.

V4 EXTRACTOR PROFILE — does the extractor_profile_id you propose exist in
   seeds/reference/extractor_profiles.yaml? Quote the line. If not, the template is invalid.

V5 LANGUAGE — what are this canton's official languages? Use only sources in this repo (the
   jurisdictions seed, existing templates, docs). \`language\` selects the LexFind query language and
   \`language_codes\` describes the corpus. A German-only query against a French-speaking canton
   returns nothing and reads exactly like "this canton has no dog law". Flag every canton where the
   committed evidence does not settle the language, especially the bilingual and trilingual ones.

V6 SEARCH SHAPE — Swiss systematic numbering is PER CANTON, not national: the dog law is 554.5 in
   ZH, 916.31 in BE and 365.100 in BS. A numeric prefix that enumerates a branch in one canton is
   meaningless in another, which is why the BE and BS templates search a title keyword instead of a
   number (source_blueprints.yaml, in the comment above lexfind_api_be_hunde). So: propose a
   keyword search, not a systematic prefix, unless you can cite this canton's actual number from a
   committed source. State which you chose and why.
   Also decide between a topic template (search_text) and a whole-corpus one
   (enumeration: systematic_digit_union, as in lexfind_api_zh_full) — and read that template's cost
   comment before proposing the second. It is ~40 discovery requests plus a PDF fetch per act
   (~1377 for ZH, including 433 repealed) against an API whose terms are unconfirmed. That is an
   operator decision, not a default.

V7 COMPLIANCE POLICY — which compliance_policy applies to lexfind.ch? Read
   seeds/reference/compliance_policies.yaml and say whether a suitable policy exists or whether one
   must be authored. If it must be authored, that is a blocker, not a field you fill in.

V8 SHIPS SHUT — assert your draft carries \`enabled: false\` and say why in one line (ADR-0030: the
   config key is turned per template against that template's own acceptance evidence; an inherited
   default is not evidence). A draft with \`enabled: true\` is a defect in YOUR output.
`

const DRAFT_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['cantons'],
  properties: {
    cantons: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['canton', 'status', 'template_yaml', 'validations'],
        properties: {
          canton: { type: 'string' },
          status: {
            type: 'string',
            enum: ['READY_FOR_HUMAN_REVIEW', 'BLOCKED_NEEDS_HUMAN_DECISION', 'INVALID'],
          },
          template_name: { type: 'string' },
          template_yaml: {
            type: 'string',
            description: 'The draft template as YAML text. UNKNOWN fields written as UNKNOWN, never guessed.',
          },
          validations: {
            type: 'array',
            items: {
              type: 'object',
              additionalProperties: false,
              required: ['check', 'result'],
              properties: {
                check: { type: 'string', enum: ['V1', 'V2', 'V3', 'V4', 'V5', 'V6', 'V7', 'V8'] },
                result: { type: 'string', enum: ['OK', 'UNKNOWN', 'BLOCKER', 'INVALID'] },
                anchor: { type: 'string' },
                detail: { type: 'string' },
              },
            },
          },
          blockers: {
            type: 'array',
            description: 'What a human must decide or supply, and the exact action that would settle it.',
            items: { type: 'string' },
          },
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
        required: ['canton', 'sound', 'problems'],
        properties: {
          canton: { type: 'string' },
          sound: { type: 'boolean', description: 'false if ANY field was guessed rather than sourced.' },
          problems: { type: 'array', items: { type: 'string' } },
          invented_fields: {
            type: 'array',
            description: 'Fields whose value you could not trace to a committed source. The critical output.',
            items: { type: 'string' },
          },
        },
      },
    },
  },
}

// ── run ──────────────────────────────────────────────────────────────────────
phase('Ground')

const ground = await agent(
  `${HOUSE}
${REFERENCE}

Establish the ground truth. Do not draft anything yet. Report:

1. Every blueprint template that already targets a Swiss canton, with its provider, its template
   name, its entity_ids, and its \`enabled\` value. Quote file:line.
2. Which cantons therefore ALREADY have a template, and which of the 26 do not.
3. Every cantonal entity id committed anywhere in this repo, with the file:line it comes from.
   This is the list a later agent is forbidden to extend by inference — make it exhaustive.
4. The exact field set of a lexfind_api template, read from the committed examples AND from what
   lexfind_api_provider.py actually reads out of the acquisition spec. Note any field the provider
   reads that no committed template sets, and any field a template sets that the provider ignores.
5. What test_blueprint_provider_parity.py requires of a template for it to be valid.
6. Confirm, by reading docs/architecture/ch-acquisition-coverage-status.md, whether the cantonal
   rung is served by lexfind_api or by canton_http, and quote the line that settles it. If that
   document contradicts the header comment of this workflow script, SAY SO — the document wins.

Return compact structured prose with citations. Contact nothing.`,
  { label: 'ground truth' },
)

const CANTONS = [
  'ag', 'ai', 'ar', 'bl', 'fr', 'ge', 'gl', 'gr', 'ju', 'lu', 'ne', 'nw', 'ow',
  'sg', 'sh', 'so', 'sz', 'tg', 'ti', 'ur', 'vd', 'vs', 'zg',
]
let targets = ONLY || CANTONS
if (ONLY) log(`args.cantons restricted the run to: ${targets.join(', ')}`)

const batches = []
for (let i = 0; i < targets.length; i += PER_AGENT) {
  batches.push(targets.slice(i, i + PER_AGENT))
}
log(`${targets.length} canton(s) → ${batches.length} batch(es) of ≤${PER_AGENT}; ~${batches.length * 2 + 2} agents`)

const results = await pipeline(
  batches,

  (batch, _o, idx) =>
    agent(
      `${HOUSE}
${REFERENCE}

You are drafting lexfind_api blueprint templates for cantons: ${batch.join(', ')}
(batch ${idx + 1} of ${batches.length}).

GROUND TRUTH established by another agent — a starting map, NOT fact. Re-open anything you rely on,
and in particular re-read the committed entity-id list yourself before using any id:
${ground}

${CHECKS}

Produce one entry per canton. Status rules, applied strictly:
  BLOCKED_NEEDS_HUMAN_DECISION — any validation returned BLOCKER or UNKNOWN. This is the EXPECTED
      outcome for most cantons, because the entity id is not in this repo. A blocked entry is a
      GOOD result: it is a precise, actionable question. Do not manufacture a value to avoid it.
  READY_FOR_HUMAN_REVIEW — every validation OK, every field traced to a committed source, and the
      draft still requires a human to author it, run acceptance and flip the key.
  INVALID — the template cannot be valid as drafted (e.g. no such extractor profile).

The single worst thing you can do here is emit a plausible entity id. Write UNKNOWN.`,
      { phase: 'Draft', label: `draft ${batch.join('+')}`, schema: DRAFT_SCHEMA },
    ),

  async (draft, batch, idx) => {
    if (!draft) return null
    const panel = await agent(
      `${HOUSE}

You are the sceptic for batch ${idx + 1} (${batch.join(', ')}). YOUR JOB IS TO FIND INVENTED FACTS.

DRAFTS:
${JSON.stringify(draft.cantons, null, 2)}

For every canton, and every non-obvious field in its template — entity_ids above all, then
corpus_id, extractor_profile_id, language, language_codes, search_text, compliance policy — trace
the value to a committed source YOURSELF and quote the file:line. A value you cannot trace is an
INVENTED FIELD, and you must list it, even if it looks right.

Specific traps:
  - An entity id that is not one of the three committed ones (ZH=26, BE=4, BS=6) and is not quoted
    from a file in this repo. Any such id is invented, however plausible its derivation.
  - A canton marked READY whose language was assumed rather than sourced — a wrong query language
    returns an empty result that reads as "no such law".
  - A systematic-number prefix carried over from another canton. Swiss numbering is per canton.
  - \`enabled: true\` anywhere, or a draft that omits \`enabled\`.
  - A status of READY_FOR_HUMAN_REVIEW where any validation is UNKNOWN.
  - Any sign the drafter contacted a network host. Say so loudly if you see one.

sound = false if ANY field was guessed. Default to sound = false when you cannot trace a value
yourself. Absence of proof is refutation here.`,
      { phase: 'Refute', label: `refute ${batch.join('+')}`, schema: REFUTE_SCHEMA },
    )
    return { draft, verdicts: (panel && panel.verdicts) || [] }
  },
)

const ok = results.filter(Boolean)
const lost = batches.length - ok.length
if (lost > 0) log(`⚠ ${lost} batch(es) produced nothing — those cantons were NOT assessed`)

const entries = []
ok.forEach((r) => {
  ;(r.draft.cantons || []).forEach((c) => {
    const v = r.verdicts.find((x) => x.canton === c.canton)
    const invented = (v && v.invented_fields) || []
    // A draft with an untraceable field is demoted, never presented as ready.
    const status = v && v.sound === false ? 'BLOCKED_NEEDS_HUMAN_DECISION' : c.status
    entries.push({
      ...c,
      status,
      invented_fields: invented,
      sceptic_problems: (v && v.problems) || (v ? [] : ['no sceptic verdict — treat as unverified']),
    })
  })
})

const ready = entries.filter((e) => e.status === 'READY_FOR_HUMAN_REVIEW')
const blocked = entries.filter((e) => e.status === 'BLOCKED_NEEDS_HUMAN_DECISION')
log(`${entries.length} assessed: ${ready.length} ready for human review, ${blocked.length} blocked`)

phase('Memo')
const memo = await agent(
  `${HOUSE}

Write the DECISION MEMO. This memo is the deliverable. There is no action to take.

ASSESSED CANTONS (sceptic verdicts already folded in; anything with invented_fields has already
been demoted to BLOCKED):
${JSON.stringify(entries, null, 2)}

NOT ASSESSED AT ALL (batches that produced nothing): ${lost}

Write exactly this and nothing else:

1. WHAT A HUMAN MUST DECIDE — numbered, most consequential first. Each item states the decision,
   who it belongs to, and what it unblocks. At minimum this must include:
     a. Whether to make the \`entities/extended\` call to LexFind at all, given that LexFind's terms
        were never confirmed with the Schweizerische Staatsschreiberkonferenz. Give the exact call,
        its size (one request), and note that it is the single call that unblocks every blocked
        canton at once. Do not make it.
     b. Whether a compliance policy for lexfind.ch exists or must be authored, per V7.
     c. Whether whole-corpus enumeration is in scope, with its measured cost (~40 discovery
        requests plus a PDF per act) — an operator decision, not a default.
   Anything else your agents surfaced as a blocker.

2. READY FOR REVIEW — the cantons whose every field traces to a committed source. For each: the
   template YAML in a fenced block, and the file:line of each non-obvious field's source. State
   clearly that this is DRAFT TEXT for a human to paste — nothing was written to the repo.

3. BLOCKED — a table: canton | what is missing | the one action that would settle it. Group the
   ones blocked on the same thing together, so the reader sees that one decision clears many.

4. WHAT THIS RUN DID NOT ESTABLISH — unassessed batches, UNKNOWN validations, and every field any
   sceptic could not trace. Do not round this up.

5. THE STEPS THIS WORKFLOW CANNOT TAKE — restate, in three lines: an acceptance run per canton must
   be dispatched by an operator; the evidence bundle must be captured under docs/runbooks/evidence/;
   \`enabled: true\` is flipped by a human against that evidence (ADR-0030). No agent does any of these.

Terse. No preamble, no emoji, no enthusiasm. Do not write any file, do not open a PR, do not
contact any host.`,
  { label: 'decision memo' },
)

return memo
