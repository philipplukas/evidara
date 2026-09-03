// Surface weakness sweep — signature-driven discovery. Pick a lens, grep the repo for that lens's
// failure signature, verify every hit adversarially, rank by blast radius, cap.
//
// WHY ONE SCRIPT AND NOT THREE. Dead declarations, silent degradations and per-request cost are
// three different defects, but they are ONE orchestration: enumerate candidate sites by a
// repo-specific signature, refute each, rank, cap. Three scripts differing only in a prompt string
// would be exactly the parallel abstraction AGENTS.md rule 3 forbids ("edit over duplicate"). The
// lens is data; the harness is the workflow.
//
// THE LENSES, each grounded in something this repo actually shipped:
//
//   dead-declaration    A field, config knob or export that is DECLARED with no producer, or no
//                       consumer. Three instances surfaced in one session: `delegates_to` declared
//                       in the index mapping with no writer anywhere; `di_overrides.quarantine_min_*`
//                       read by document-intelligence and emitted by nobody; a `searchParamsCache`
//                       documented as the single source of truth with zero consumers in src/.
//                       A declared-and-empty field is worse than an absent one: OpenSearch returns
//                       an empty bucket rather than an error, so it reads as "none exists".
//
//   silent-degradation  A failure path that substitutes instead of refusing. `except Exception`
//                       paired with a debug log; `or 0` / `or ""` fallbacks; a 200 trusted without
//                       a content check; a default that stands in for a missing value; `# pragma:
//                       no cover`. This repo has an explicit history: #631, #675, #713, #728, plus
//                       a `logger.debug` swallow that would have silently reverted every production
//                       read to a crashing path, and a provenance fallback that substituted the
//                       mirror's URL for the source's.
//
//   request-path-cost   Blocking I/O, network round-trips and unbounded work on a per-request path.
//                       A blocking region lookup measured at 4,114 ms was introduced onto a
//                       per-document read path — roughly 8 s per document fetch — and was latent
//                       only because one environment variable happened to be set.
//
//   frontend-contract   The statically checkable half of frontend quality: hardcoded colours where
//                       AGENTS.md requires var(--token), missing locale keys, props no test ever
//                       renders, exports nothing imports. The half that needs a running browser
//                       (keyboard reachability, contrast, focus visibility) is NOT here — see
//                       visual-critique.js and the gap noted in README.md.
//
// Read-only: greps and reads. It never mutates a file. Proving a guard is decoration by BREAKING it
// is guard-efficacy-mutation.js, which does that in a throwaway worktree.

export const meta = {
  name: 'surface-weakness-sweep',
  description:
    'Signature-driven hunt for dead declarations, silent degradations, per-request cost or frontend contract drift — every hit refuted before it is reported',
  whenToUse:
    'To answer "what is weak here?" about a surface, rather than "is this diff right?". Pick a lens with args.lenses; the default sweeps all four.',
  phases: [
    { title: 'Aim', detail: 'resolve lenses and surfaces into a bounded work list' },
    { title: 'Hunt', detail: 'one agent per lens/surface pair, grepping its failure signature' },
    { title: 'Refute', detail: 'an independent sceptic tries to kill each hit' },
    { title: 'Rank', detail: 'top findings by blast radius, with what was dropped stated' },
  ],
}

const A = args || {}
const ALL_LENSES = ['dead-declaration', 'silent-degradation', 'request-path-cost', 'frontend-contract']
const LENSES = (Array.isArray(A.lenses) ? A.lenses : A.lens ? [A.lens] : ALL_LENSES).filter(
  (l) => ALL_LENSES.indexOf(l) !== -1,
)
// 'auto' lets the Aim agent choose the surface for each lens. Pass explicit paths to pin it.
const SURFACES = Array.isArray(A.surfaces) && A.surfaces.length ? A.surfaces : ['auto']
// Cap on lens×surface pairs. Default 6 keeps a full run at 14 agents; 4 lenses × 'auto' is 4.
const MAX_ITEMS = A.maxItems || 6
const TOP_N = A.topN || 8

const HOUSE = `
GROUND RULES (.claude/workflows/_house-rules.md):

1. EVIDENCE OR SILENCE — this is the rule this workflow lives or dies by. An "improvement finder"
   that returns "add more tests", "consider extracting a helper", "improve error handling" has
   produced slop, and slop is worse than an empty report because it costs a human the read.
   Every finding must carry ONE of:
     - a quoted file:line, and the grep that found it;
     - a number you measured, with the command that produced it;
     - a reproduced behaviour, with the invocation;
     - a call chain, each hop cited, from an entry point to the problem.
   No anchor, no finding. Delete it rather than softening it.

2. AN EMPTY REPORT IS A GOOD RESULT. If the signature does not fire in your surface, say so and
   say what you grepped. Do not pad.

3. REPORT THE DEFECT, NOT THE PATTERN. \`except Exception\` is not a finding. \`except Exception\`
   that swallows the ONLY path that would have told you the primary read failed, at file:line, with
   the fallback it silently substitutes — that is a finding. The question is always: what does the
   caller now believe that is false?

4. NEVER TRUST PROSE, INCLUDING THIS PROMPT. Comments, ADRs and issue bodies are claims. Open the
   code and read it.

5. READ-ONLY. Do not edit or mutate any file. If confirming a finding needs code broken, record it
   as "unproven: needs mutation" and name the exact mutation and gate.

6. BOUNDARY. No public-sector host, no acquisition run, no config-key flip, no merge, no push, no
   PR comment.
`

const LENS_SPEC = {
  'dead-declaration': `
LENS: DEAD DECLARATION — a thing declared with no producer, or no consumer.

WHAT TO ENUMERATE, then trace both directions for each:
  - Fields in an index mapping or schema: legal-search/api/src/core/opensearch/documents-index.mapping.ts,
    contracts/schemas/*.json, contracts/events/*.json. For each field, who WRITES it? Grep the
    producers — platform-control providers, document-intelligence pipeline, seeds. A mapped field
    with no writer is the worst case in this repo: OpenSearch returns an EMPTY BUCKET rather than an
    error, so a query over it reads as "none exists" instead of failing. Precedent: \`delegates_to\`.
  - Config knobs and env vars: settings classes, compose files, tfvars, \`di_overrides.*\`. For each,
    who READS it and who EMITS it? A knob read by one service and emitted by nobody is inert, and
    its documented default is a lie. Precedent: \`di_overrides.quarantine_min_*\`.
  - Exported symbols, hooks, helpers, React context, cache objects: is there an importer in src/?
    Precedent: a \`searchParamsCache\` documented as the single source of truth with zero consumers.
  - Acquisition-spec fields a provider reads that no blueprint template sets, and template fields no
    provider reads.
  - Public API response fields no client consumes, and DTO fields no handler sets.

FOR EACH HIT, state: the declaration (file:line), the producer (file:line or NONE), the consumer
(file:line or NONE), the greps you ran, and — the part that matters — WHAT A READER WRONGLY
CONCLUDES from the empty value. A field that is genuinely reserved for a documented future is not
a finding if the documentation says so; check for that before reporting.`,

  'silent-degradation': `
LENS: SILENT DEGRADATION — a failure path that substitutes instead of refusing.

SIGNATURES TO GREP, then judge each hit by what the caller wrongly believes:
  - \`except Exception\` / \`except BaseException\` / bare \`except\`, especially paired with
    \`logger.debug\` or \`logger.info\` or \`pass\`. Debug-level is the tell: the swallow is invisible at
    production log level. Ask: if this fires in production, what silently changes? Precedent: a
    \`logger.debug\` swallow that would have reverted every production read to a crashing path.
  - \`or 0\`, \`or ""\`, \`or []\`, \`or {}\`, \`?? 0\`, \`|| ''\`, \`.get(k, <default>)\` where the default is
    indistinguishable from a real value. A count that falls back to 0 reports "none found".
  - A 2xx trusted without checking the body: a fetch whose status is checked but whose content type,
    magic number or length is not. This repo has a named instance of the general class (#716: a
    metadata-only HTML page served where a PDF was expected) and a guard built for it at
    src/acquisition_core/artifact_guard.py — so ALSO check which fetch paths do NOT go through it.
  - A default that SUBSTITUTES rather than refuses: a fallback URL, a fallback identifier, a
    fallback tenant, a fallback date. Precedent: a provenance fallback that substituted the
    mirror's URL for the source's, which is a correctness bug wearing a robustness costume.
  - \`# pragma: no cover\`, \`istanbul ignore\`, \`c8 ignore\`, \`eslint-disable\`, \`biome-ignore\`,
    \`# type: ignore\`, \`@ts-expect-error\`: each is a place someone turned a check off. Is the reason
    still true?
  - \`try\` around an import or a feature detection that falls back to a lesser code path.

RANK BY BLAST RADIUS: how far does the wrong value travel before anyone could notice? A swallow in
a leaf logger is low. A swallow that changes what gets indexed, what gets attributed, or whether a
guard runs is a ship-blocker.`,

  'request-path-cost': `
LENS: REQUEST-PATH COST — blocking I/O, network round-trips and unbounded work on a per-request path.

METHOD — you must build a CALL CHAIN, not an impression:
  1. Enumerate the entry points: NestJS controllers in legal-search/api/src/**, FastAPI routers in
     platform-control/src/platform_control/routers/**, Next.js server components, route handlers and
     middleware.
  2. From each, follow the calls. You are looking for, ON the request path:
       - a synchronous/blocking call in an async handler (a blocking SDK call, a sync file read, a
         sync DNS or metadata lookup — a blocking cloud region/credential lookup measured 4,114 ms
         on a per-document read path here, roughly 8 s per fetch, latent only because one env var
         happened to be set);
       - a network round-trip per request that could be hoisted, cached or done at startup;
       - work unbounded by input size: a query with no limit, a loop over a full result set, an
         N+1, a full-collection scan, an unbounded JSON parse;
       - a retry or timeout with no ceiling.
  3. For each candidate, check whether something SHORT-CIRCUITS it — a module-level cache, a
     memoised singleton, an env var that is always set in deployment, a warm path. If it is
     short-circuited, the finding is that it is LATENT, and the condition that would expose it. Say
     which. A latent 8-second call is still a finding; a mischaracterised one is not.
  4. Cite the chain: entry point file:line -> ... -> the expensive call file:line. Every hop.
  5. Where you can measure without deploying anything (a local script, an existing benchmark, a
     test that times it), measure and give the command. Where you cannot, say the number is
     inferred and from what.

Do NOT report micro-optimisations, allocation counts or style. Only per-request cost with a chain.`,

  'frontend-contract': `
LENS: FRONTEND CONTRACT — the statically checkable half of frontend quality.

Surfaces: legal-search/frontend/src, platform-control/admin/src, marketing/src, styles/.

WHAT TO ENUMERATE:
  - HARDCODED COLOURS where a token is required. AGENTS.md: "Design tokens live in globals.css as
    CSS custom properties. Use var(--token) everywhere, never hardcoded colors", and the review
    guidance lists hardcoded tokens as a flag. Grep for hex literals, rgb(/rgba(, hsl(, and Tailwind
    palette classes (text-slate-500, bg-gray-100 ...) in src/ and styles/. Cross-check each against
    the token files: styles/tokens/tokens.css and each surface's globals.css. A colour that has a
    token and does not use it is a finding with a one-line fix; a colour with NO token is a finding
    about the token set. Report which.
  - MISSING LOCALE KEYS. Find the locale/message files. Every key referenced in code must exist in
    EVERY locale, and every key in a locale should be referenced. A key missing from one locale
    renders as the key name or as nothing, and no type checker sees it.
  - PROPS NO TEST RENDERS. For each component, list its props, then grep its test files for which
    props are ever passed. A prop no test ever supplies is untested surface; a prop no CALLER ever
    supplies is dead (report it under dead-declaration terms).
  - STATES NEVER EXERCISED. For components that can be empty, loading, error, or given very long
    content: is there a test or a committed visual baseline for each state? The baselines under
    legal-search/frontend/e2e/visual.spec.ts-snapshots/ include empty-state and error-state at two
    widths — use them as the reference for which states are covered, and report components with no
    coverage of a state they can reach.
  - EXPORTS NOTHING IMPORTS, and components rendered from nowhere.

DO NOT opine on aesthetics, spacing, hierarchy or "polish" from source. That requires rendered
output and belongs to visual-critique.js. Anything you cannot check statically, leave out.`,
}

const HIT_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['lens', 'searched', 'findings'],
  properties: {
    lens: { type: 'string' },
    searched: { type: 'string', description: 'The greps and paths you ran. Required even when nothing fired.' },
    findings: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['title', 'anchor', 'evidence', 'wrong_belief', 'blast_radius'],
        properties: {
          title: { type: 'string' },
          anchor: { type: 'string', description: 'file:line, quoted.' },
          evidence: { type: 'string', description: 'The grep/chain/number that establishes it.' },
          wrong_belief: {
            type: 'string',
            description: 'What a caller, operator or reader now believes that is false. The heart of the finding.',
          },
          blast_radius: { type: 'string', enum: ['ship-blocker', 'high', 'medium', 'low'] },
          latent_because: { type: 'string', description: 'What currently masks it, if anything.' },
          fix: { type: 'string' },
          unproven: { type: 'string', description: 'The mutation or measurement that would settle it, if you could not.' },
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
        required: ['anchor', 'refuted', 'reason'],
        properties: {
          anchor: { type: 'string' },
          refuted: { type: 'boolean' },
          reason: { type: 'string' },
          missed_producer_or_consumer: { type: 'string', description: 'The writer/reader/short-circuit the hunter missed.' },
          severity_after_check: { type: 'string', enum: ['ship-blocker', 'high', 'medium', 'low', 'none'] },
        },
      },
    },
  },
}

const SEVERITY = ['ship-blocker', 'high', 'medium', 'low', 'none']

// ── run ──────────────────────────────────────────────────────────────────────
phase('Aim')
if (LENSES.length === 0) {
  log(`⚠ no valid lens in args.lenses — valid values are: ${ALL_LENSES.join(', ')}`)
  return `No valid lens selected. Pass args.lenses as a subset of: ${ALL_LENSES.join(', ')}`
}

let items = []
for (const lens of LENSES) {
  for (const surface of SURFACES) {
    items.push({ lens, surface })
  }
}
if (items.length > MAX_ITEMS) {
  const dropped = items.slice(MAX_ITEMS).map((i) => `${i.lens}@${i.surface}`)
  log(`⚠ CAPPED at maxItems=${MAX_ITEMS}. NOT SWEPT: ${dropped.join(', ')}`)
  items = items.slice(0, MAX_ITEMS)
}

const aim = await agent(
  `${HOUSE}

Aim the sweep. Do NOT hunt anything yet.

Lenses selected: ${LENSES.join(', ')}
Surfaces requested: ${SURFACES.join(', ')}${SURFACES[0] === 'auto' ? ' (you choose)' : ''}

1. For each lens, name the concrete paths worth sweeping and, briefly, why. Use the repo's real
   layout — read AGENTS.md's component list rather than guessing. Prefer surfaces where the lens's
   signature plausibly fires over surfaces that are merely large.
2. Report what tooling is available for grepping and reading, and whether Node 22 and uv are
   present (some lenses want to read a lockfile or run a read-only script).
3. Name, per lens, the two or three greps you would start with. The hunters will refine them, but
   a bad starting grep wastes an agent.
4. Warn about known FALSE-POSITIVE generators for each lens in this repo specifically — e.g. a
   field that is genuinely reserved and documented as such; a swallow that is deliberate and
   commented with a reason that is still true; a blocking call that only runs at module load and
   not per request. The hunters will be told to check for these.

Return compact structured prose with paths. Nothing else.`,
  { label: 'aim the sweep' },
)

log(`${items.length} lens/surface pair(s); ~${items.length * 2 + 2} agents`)

const results = await pipeline(
  items,

  (item) =>
    agent(
      `${HOUSE}

${LENS_SPEC[item.lens]}

SURFACE: ${item.surface === 'auto' ? 'choose from the aiming notes below' : item.surface}

AIMING NOTES from another agent — a starting map, not fact. Re-check the paths exist:
${aim}

Hunt. Fill \`searched\` with the greps and paths you actually ran, even if nothing fired — that
field is how a reader knows an empty result means "swept and clean" rather than "did not look".

For every hit, the \`wrong_belief\` field is mandatory and is the test of whether you have a finding
at all: name what a caller, an operator or a future reader now believes that is false. If you
cannot fill it, you have found a pattern, not a defect — drop it.

Check each hit against the false-positive generators before reporting it. Rank your own hits by
blast radius and return at most 6; say in \`searched\` how many you dropped and why.`,
      { phase: 'Hunt', label: `${item.lens} @ ${item.surface}`, schema: HIT_SCHEMA },
    ),

  async (hit, item) => {
    if (!hit || !hit.findings || hit.findings.length === 0) {
      return { lens: item.lens, surface: item.surface, searched: (hit && hit.searched) || 'nothing reported', survivors: [], killed: 0 }
    }
    const panel = await agent(
      `${HOUSE}

You are the sceptic for the "${item.lens}" hunt on ${item.surface}. YOUR JOB IS TO KILL THESE.

${JSON.stringify(hit.findings, null, 2)}

For each, do the work the hunter should have done and probably did not:
  - Open the anchor. Is the line number current and does it say what is claimed?
  - dead-declaration: search HARDER for a producer or consumer. Try the field name in other cases
    (snake_case, camelCase), in generated files, in YAML seeds, in SQL, in test fixtures, in
    Terraform, in compose files. One hit anywhere kills the finding. Also check whether the
    declaration is documented as reserved.
  - silent-degradation: is the swallow deliberate and still correct? Read the comment above it and
    then verify the comment against the code. Is there a re-raise, a metric, a sentinel, or an
    outer handler that makes it visible after all?
  - request-path-cost: is the call actually on the request path, or on a startup/module-load path?
    Is there a cache, memoisation, singleton or always-set env var that short-circuits it? A
    mischaracterised chain is the commonest false positive here — check every hop.
  - frontend-contract: does the "hardcoded" colour have a token at all? Is the locale key supplied
    by a fallback chain? Is the "untested prop" covered by a visual baseline rather than a unit test?

refuted = true unless you personally re-derived it. DEFAULT TO refuted = true WHEN UNCERTAIN.
When you find the producer/consumer/short-circuit the hunter missed, put it in
missed_producer_or_consumer — that is more useful than the kill alone. Correct the severity too:
a real finding can still be low blast radius.`,
      { phase: 'Refute', label: `refute ${item.lens}`, schema: REFUTE_SCHEMA },
    )
    const verdicts = (panel && panel.verdicts) || []
    const survivors = []
    let killed = 0
    hit.findings.forEach((f) => {
      const v = verdicts.find((x) => x.anchor === f.anchor)
      if (!v) {
        survivors.push({ ...f, lens: item.lens, status: 'UNVERIFIED — no sceptic verdict' })
        return
      }
      if (v.refuted) {
        killed++
        return
      }
      survivors.push({
        ...f,
        lens: item.lens,
        status: 'SURVIVED',
        blast_radius: v.severity_after_check && v.severity_after_check !== 'none' ? v.severity_after_check : f.blast_radius,
        sceptic_note: v.reason,
      })
    })
    log(`${item.lens}: ${survivors.length} survived, ${killed} refuted`)
    return { lens: item.lens, surface: item.surface, searched: hit.searched, survivors, killed }
  },
)

const ok = results.filter(Boolean)
const lost = items.length - ok.length
if (lost > 0) log(`⚠ ${lost} lens/surface pair(s) produced nothing — NOT SWEPT, not clean`)

const all = ok.flatMap((r) => r.survivors)
all.sort((a, b) => SEVERITY.indexOf(a.blast_radius) - SEVERITY.indexOf(b.blast_radius))
const top = all.slice(0, TOP_N)
if (all.length > top.length) log(`capped at ${TOP_N}: dropped ${all.length - top.length} lower-blast-radius survivors`)

phase('Rank')
const report = await agent(
  `${HOUSE}

Write the surface weakness report.

SURVIVORS (each already re-derived by an independent sceptic; ${all.length} survived,
${ok.reduce((n, r) => n + r.killed, 0)} refuted — refuted findings must NOT reappear):
${JSON.stringify(top, null, 2)}

WHAT WAS SEARCHED, per lens (this is how a reader tells "clean" from "not looked at"):
${ok.map((r) => `  ${r.lens} @ ${r.surface}: ${r.searched}`).join('\n')}

PAIRS THAT PRODUCED NOTHING AT ALL: ${lost}

Write exactly this and nothing else:

1. HEADLINE — one line per lens: swept / N survived / M refuted. Numbers only.

2. FINDINGS — numbered, worst blast radius first, at most ${TOP_N}. Each in five lines:
     WHAT:    <one sentence>
     WHERE:   <file:line>
     WHY IT IS WRONG: <what a caller/operator/reader now believes that is false>
     LATENT:  <what masks it today, or "not masked">
     FIX:     <the narrowest change>

3. UNPROVEN — findings that need a mutation or a measurement this read-only workflow will not
   perform. Give the exact mutation and gate for each, so guard-efficacy-mutation.js can be
   pointed at it.

4. COVERAGE — what was swept, what was capped out, what produced nothing. State plainly that this
   is a sample of a signature, not an exhaustive audit. Do not round it up.

Terse. No preamble, no emoji, no praise, no "consider". Every finding carries an anchor or it does
not appear. If a lens found nothing, say "swept, nothing survived" and name the greps — that is a
result, not a failure. Do not edit any file and do not open a PR.`,
  { label: 'weakness report' },
)

return report
