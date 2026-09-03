// Guard efficacy — break each guard on purpose and report the ones no test notices.
//
// This was the single most productive technique available. It is what proved a feature could be
// deleted entirely with all 286 tests still passing; what proved a deny-assertion probed a
// nonexistent key and could therefore never fail; and what proved an operator kill-switch could be
// flipped with exit 0. None of those is visible in a diff, in a green CI run, or to a reviewer
// reading the test for quality. All three are obvious within seconds of breaking the code.
//
// Systematised, it answers a question nothing else here answers: WHICH OF OUR GUARDS ARE DECORATION?
//
// ── THE FALSE POSITIVE THAT WOULD DESTROY THIS WORKFLOW ──────────────────────
// "I deleted the guard and the tests still passed" is worthless if the tests DID NOT RUN. A fresh
// git worktree has no node_modules and no populated virtualenv; a gate invoked there can exit
// non-zero on setup, or skip a whole section, and an agent that is not paying attention reads that
// as "nothing noticed". That would report every guard in the repo as decoration.
//
// So this script is built around a BASELINE: before mutating anything, run the gate UNMUTATED and
// require it to be green, with a test count. If the baseline is not demonstrably green, the batch
// is abandoned and reported as DID_NOT_RUN. Every mutation result is then a comparison against a
// known-good count, not against an assumption.
//
// ── COST ─────────────────────────────────────────────────────────────────────
// Every mutating agent runs with isolation: 'worktree' — a fresh checkout per agent, ~200-500ms
// setup plus disk, and dependencies must be installed inside it before any gate can run. That is
// deliberate: mutation and parallelism cannot share a tree, and
// docs/process/max-parallel-execution.md's serialization rules exist for exactly this reason.
// Default is 5 batches → 12 agents, 10 worktrees. Scope it with args.target.
//
// It never pushes, commits, merges or leaves a mutation behind.

export const meta = {
  name: 'guard-efficacy-mutation',
  description:
    'Delete or invert each guard in a chosen surface and report the ones no test notices — mutation-tested in throwaway worktrees',
  whenToUse:
    'When you need to know whether a surface\'s tests actually hold it, not whether they pass. Expensive (a git worktree per agent) — scope it with args.target.',
  phases: [
    { title: 'Inventory', detail: 'enumerate the guards in the target surface and batch them' },
    { title: 'Mutate', detail: 'per batch, in its own worktree: baseline, then break each guard' },
    { title: 'Confirm', detail: 'an independent agent re-applies each unnoticed mutation in a fresh worktree' },
    { title: 'Rank', detail: 'decoration first — guards nothing would notice losing' },
  ],
}

const A = args || {}
// What to mutate. A path, a module, or a named concept. Scope this: mutating the whole repo is
// neither affordable nor useful.
const TARGET = A.target || 'platform-control/src/acquisition_core and its provider call sites'
// The CI-equivalent gate for the target. If you do not pass one, the Inventory agent derives it
// from CLAUDE.md and says which it chose.
const GATE = A.gate || null
const BATCHES = Math.max(1, Math.min(6, A.batches || 5))
// Guards per batch. A batch of 8 mutations at ~1 gate run each is already a long agent.
const PER_BATCH = A.guardsPerBatch || 8

const HOUSE = `
GROUND RULES (.claude/workflows/_house-rules.md), plus the ones specific to mutation:

1. YOU ARE IN YOUR OWN THROWAWAY GIT WORKTREE. Mutate freely inside it. Never \`git commit\`,
   \`git push\`, \`git merge\`, or touch any other checkout. Do not \`git checkout\` a different branch.

2. BASELINE FIRST, ALWAYS. Before you mutate anything:
     a. Install what the gate needs IN THIS WORKTREE. A worktree inherits NOTHING: no
        node_modules, no populated virtualenv. For JS surfaces that means \`npm ci\` in the surface
        directory, with Node 22 (\`export NVM_DIR="$HOME/.config/nvm"; . "$NVM_DIR/nvm.sh"; nvm use 22\`
        — SEMICOLONS, not &&, because nvm.sh returns 3). For Python, \`uv\` resolves per-project.
     b. Run the gate UNMUTATED. Record the exact command, the exit code, and THE TEST COUNT.
     c. If the baseline is not green with a plausible test count, STOP THIS BATCH. Report every
        guard in it as DID_NOT_RUN with the reason. Do not mutate anything. Do not report a single
        "no test noticed".
   A "no test noticed" result against a baseline that was never green is the one output of this
   workflow that would be actively harmful. It would mark working guards as decoration.

3. THE COUNT IS THE EVIDENCE. After each mutation, compare against the baseline: same command,
   same exit code, SAME NUMBER OF TESTS RUN. If the count dropped, tests were skipped or failed to
   collect — that is DID_NOT_RUN for this mutation, not "unnoticed". Collection errors are the
   commonest way a mutation appears to go unnoticed.

4. REVERT AFTER EVERY MUTATION. \`git checkout -- <path>\` (or \`git stash\`/\`git checkout -- .\`),
   then \`git status --short\` and confirm it is clean before the next mutation. A leaked mutation
   contaminates every result after it. Report the final \`git status --short\`.

5. ONE MUTATION AT A TIME. Never stack two. If the tree is dirty when you start a mutation, stop
   and say so.

6. MUTATE THE GUARD, NOT THE TEST. Never edit a test file. If you find yourself wanting to, the
   guard you picked is not a guard.

7. BOUNDARY. No public-sector host, no acquisition run, no config-key flip in a way that reaches a
   real environment, no push, no PR comment. Compose/local only, and prefer not running services
   at all.
`

const WHAT_IS_A_GUARD = `
WHAT COUNTS AS A GUARD (mutate these; skip anything else):
  - A predicate that refuses: an \`if ... raise\`, an \`if ... return None/False\`, an early return that
    rejects input, a \`match\`/\`case\` default that refuses.
  - A validator: a Pydantic validator, a DTO decorator, a JSON-schema \`required\`, a NestJS pipe.
  - An assertion in production code, and any \`assert\` in a test that claims something is DENIED,
    ABSENT or REFUSED. Deny-assertions are the highest-yield target: one probed a key that did not
    exist and therefore could never fail.
  - A gate script's \`exit 1\` path, and any check whose failure is supposed to stop a build. An
    operator kill-switch that can be flipped with exit 0 is the same defect class.
  - A capture/content guard: the branches of src/acquisition_core/artifact_guard.py, a content-type
    check, a magic-number check, a size floor, a robots/host allow-list check.
  - A readiness or enablement lock: a provider's \`readiness\`, a template's \`enabled\`, and the code
    that reads them.
  - A CI condition: an \`if:\` on a job or step whose false branch silently skips a required check.

MUTATIONS TO APPLY, cheapest first — pick the one that is unambiguously wrong:
  - Invert the predicate (\`if x\` -> \`if not x\`).
  - Delete the guard block entirely.
  - Make the refusal a no-op: replace \`raise ...\` with \`pass\`, \`return False\` with \`return True\`,
    \`exit 1\` with \`exit 0\`.
  - Neutralise the value: return a constant, an empty collection, or the permissive default.
  - For a deny-assertion: change what it probes to something that certainly exists, or assert the
    opposite. If BOTH the assertion and its opposite pass, the assertion is inert — that is the
    finding, and it is a strong one.
`

const MUTATE_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['baseline', 'results'],
  properties: {
    baseline: {
      type: 'object',
      additionalProperties: false,
      required: ['command', 'green', 'detail'],
      properties: {
        command: { type: 'string' },
        green: { type: 'boolean' },
        test_count: { type: 'string' },
        detail: { type: 'string', description: 'Real output tail. If not green, why — and then no mutations were run.' },
        setup: { type: 'string', description: 'What you installed in this worktree to make the gate runnable.' },
      },
    },
    results: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['guard', 'anchor', 'mutation', 'outcome'],
        properties: {
          guard: { type: 'string' },
          anchor: { type: 'string', description: 'file:line of the guard.' },
          mutation: { type: 'string', description: 'The exact edit applied, as a diff or a one-line description.' },
          outcome: {
            type: 'string',
            enum: ['CAUGHT', 'UNNOTICED', 'DID_NOT_RUN'],
            description: 'CAUGHT = a test went red. UNNOTICED = gate stayed green at the SAME test count. DID_NOT_RUN = anything else.',
          },
          caught_by: { type: 'string', description: 'For CAUGHT: the test that failed, at file:line.' },
          test_count_after: { type: 'string' },
          evidence: { type: 'string', description: 'Real output tail.' },
          reverted: { type: 'boolean' },
        },
      },
    },
    final_git_status: { type: 'string' },
  },
}

const CONFIRM_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['verdicts'],
  properties: {
    verdicts: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['anchor', 'confirmed_unnoticed', 'reason'],
        properties: {
          anchor: { type: 'string' },
          confirmed_unnoticed: { type: 'boolean' },
          reason: { type: 'string' },
          caught_by: { type: 'string', description: 'The test the first agent missed, if you found one.' },
          blast_radius: { type: 'string', enum: ['ship-blocker', 'high', 'medium', 'low'] },
        },
      },
    },
  },
}

const SEVERITY = ['ship-blocker', 'high', 'medium', 'low']
// Sort key for blast radius. `indexOf` returns -1 for a missing or unrecognised value, which
// would sort an unlabelled finding ABOVE a ship-blocker; 99 puts it last instead.
const rank = (s) => (SEVERITY.indexOf(s) + 1 || 99)

// ── run ──────────────────────────────────────────────────────────────────────
phase('Inventory')
log(`target: ${TARGET}`)

const inventory = await agent(
  `${HOUSE}

Inventory the guards. Do NOT mutate anything — you are read-only in this step.

TARGET: ${TARGET}

${WHAT_IS_A_GUARD}

1. Enumerate every guard in the target, with file:line and a one-line description of what it
   refuses. Include deny-assertions in the target's TEST files (an assertion that something is
   absent/denied is a guard on the guard, and it is the highest-yield class).
2. Determine the CI-EQUIVALENT gate for this surface from CLAUDE.md's "Per-surface quality gates"
   table, and quote the row. ${GATE ? `The caller passed a gate to use: ${GATE} — sanity-check it against the table and say if it is narrower than CI.` : 'Choose the narrowest gate that still covers the target, and say why.'}
   Remember the traps: a bare \`uv run pytest\` is narrower than CI for platform-control;
   \`scripts/\` needs \`--with pyyaml\` or 57 tests never run; document-intelligence needs its four
   extras or test_dspy_modules.py is dropped at collection; legal-search/api's integration layer
   needs Docker.
3. Say exactly what a fresh git worktree would have to install before that gate can run, as
   concrete commands. Be honest about whether it is feasible — if the gate needs a Docker daemon
   and there is none, say so now, because every mutation result would otherwise be DID_NOT_RUN.
4. Prioritise: a guard that protects data integrity, a refusal boundary, or an operator lock
   outranks an input-validation nicety. Put the deny-assertions and the lock guards first.
5. Split into exactly ${BATCHES} batches of at most ${PER_BATCH} guards, keeping guards that share
   a gate in the same batch (so the batch pays for one baseline, not several).

Return ONLY a JSON object:
  {"gate": "<command>", "gate_row": "<quoted CLAUDE.md row>", "setup": ["<command>", ...],
   "feasible": true/false, "feasibility_note": "...",
   "batches": [[{"guard": "...", "anchor": "file:line", "refuses": "..."}, ...], ...]}`,
  { label: 'inventory guards' },
)

let inv = null
try {
  const m = String(inventory).match(/\{[\s\S]*\}/)
  inv = m ? JSON.parse(m[0]) : null
} catch (e) {
  inv = null
}
if (!inv || !Array.isArray(inv.batches) || inv.batches.length === 0) {
  log('⚠ could not parse the guard inventory — aborting rather than mutating blind')
  return `Guard inventory could not be parsed, so nothing was mutated. Raw inventory follows.\n\n${inventory}`
}
if (inv.feasible === false) {
  log(`⚠ inventory reports the gate is not runnable here: ${inv.feasibility_note || 'no reason given'}`)
}

// BATCHES is only *asked for* in the prompt, and a model-controlled fan-out is not a fan-out
// budget. An inventory returning 20 batches would spawn 42 agents, 40 of them worktree-isolated.
const batches = inv.batches.filter((b) => b && b.length).slice(0, BATCHES)
if (inv.batches.length > batches.length) {
  log(`⚠ inventory returned ${inv.batches.length} batches; capped to ${BATCHES}. The remainder was NOT MUTATED and nothing is known about those guards.`)
}
log(`${batches.length} batch(es), gate: ${inv.gate}; ~${batches.length * 2 + 2} agents, ${batches.length * 2} worktrees`)

const results = await pipeline(
  batches,

  // Stage 1 — mutate, in a throwaway worktree.
  (batch, _o, idx) =>
    agent(
      `${HOUSE}

Mutation batch ${idx + 1} of ${batches.length}. You are in your own throwaway git worktree.

GATE (run this, verbatim, from the worktree root):
    ${inv.gate}
${inv.gate_row ? `CLAUDE.md row this came from: ${inv.gate_row}\n` : ''}
SETUP this worktree needs before the gate can run:
${(inv.setup || []).map((s) => `    ${s}`).join('\n') || '    (none reported — verify for yourself)'}
${inv.feasibility_note ? `\nFEASIBILITY NOTE from the inventory: ${inv.feasibility_note}\n` : ''}
GUARDS TO MUTATE:
${JSON.stringify(batch, null, 2)}

${WHAT_IS_A_GUARD}

PROCEDURE — follow it exactly:
  1. Set up the worktree. Run the gate UNMUTATED. Record command, exit code and TEST COUNT.
  2. If the baseline is not green with a plausible test count: STOP. Set baseline.green = false,
     explain why, and return every guard with outcome DID_NOT_RUN. Do not mutate. This is a correct
     and honest outcome, and far better than a batch of false "unnoticed" results.
  3. Otherwise, for each guard in order:
       - confirm \`git status --short\` is clean;
       - apply ONE mutation (record it exactly);
       - run the gate;
       - classify:
           CAUGHT      — a test failed. Name the test at file:line.
           UNNOTICED   — the gate exited 0 AND ran the SAME number of tests as the baseline.
           DID_NOT_RUN — anything else, including a lower test count, a collection error, or a
                         failure that is clearly about setup rather than the mutation.
       - revert (\`git checkout -- <path>\`), confirm clean, move on.
  4. Report the final \`git status --short\`. It must be clean.

UNNOTICED is the finding. Be strict about it: it requires a green baseline, a green mutated run,
and matching test counts. Two out of three is DID_NOT_RUN.`,
      { phase: 'Mutate', label: `mutate batch ${idx + 1}`, schema: MUTATE_SCHEMA, isolation: 'worktree' },
    ),

  // Stage 2 — confirm the unnoticed ones independently, in a fresh worktree.
  async (mut, batch, idx) => {
    if (!mut) return null
    if (!mut.baseline || mut.baseline.green !== true) {
      log(`batch ${idx + 1}: baseline NOT green — reported as DID_NOT_RUN, correctly not as findings`)
      return { mut, verdicts: [], abandoned: true, batchNo: idx + 1 }
    }
    const unnoticed = (mut.results || []).filter((r) => r.outcome === 'UNNOTICED')
    if (unnoticed.length === 0) return { mut, verdicts: [], abandoned: false, batchNo: idx + 1 }

    const panel = await agent(
      `${HOUSE}

You are the confirmer for mutation batch ${idx + 1}. You are in a FRESH throwaway worktree, and you
share nothing with the agent that produced these claims.

CLAIMED "no test noticed" mutations:
${JSON.stringify(unnoticed, null, 2)}

GATE:
    ${inv.gate}
SETUP:
${(inv.setup || []).map((s) => `    ${s}`).join('\n') || '    (none reported — verify for yourself)'}

YOUR JOB IS TO SHOW THESE GUARDS ARE ACTUALLY TESTED. Assume the first agent's gate was broken.

  1. Establish YOUR OWN baseline: set up, run the gate unmutated, record exit code and test count.
     If your baseline is not green, set confirmed_unnoticed = false for everything with the reason
     "could not establish a baseline" — do NOT inherit the other agent's baseline.
  2. Re-apply each mutation yourself, exactly as described. Run the gate. If the count differs from
     YOUR baseline, it is DID_NOT_RUN, so confirmed_unnoticed = false.
  3. Before concluding a guard is untested, LOOK FOR THE TEST: grep the test tree for the guard's
     identifiers, its error message, its reason string. Try running a broader gate than the one
     given — a wider selection may catch it, and if it does, the finding is not "untested" but
     "not covered by this gate", which is a different and lesser finding. Say which.
  4. Revert everything. Report clean.

confirmed_unnoticed = true ONLY when your own green baseline, your own green mutated run and your
own matching test count all hold, and you failed to find any test that covers it. Default to false.
Set blast_radius by what the guard protects: data integrity, a refusal boundary or an operator lock
is ship-blocker or high; input-validation politeness is low.`,
      { phase: 'Confirm', label: `confirm batch ${idx + 1}`, schema: CONFIRM_SCHEMA, isolation: 'worktree' },
    )
    return { mut, verdicts: (panel && panel.verdicts) || [], abandoned: false, batchNo: idx + 1 }
  },
)

const ok = results.filter(Boolean)
const lost = batches.length - ok.length
if (lost > 0) log(`⚠ ${lost} batch(es) produced nothing — those guards are UNTESTED BY THIS RUN, which is not a result about them`)

const decoration = []
const caught = []
const didNotRun = []
const abandoned = []
// r.batchNo is the ORIGINAL batch index. Using the position in `ok` (post-filter) would report
// "batch 3" for what was actually batch 4 whenever an earlier batch died.
ok.forEach((r) => {
  if (r.abandoned) {
    abandoned.push(`batch ${r.batchNo}: ${(r.mut.baseline && r.mut.baseline.detail) || 'baseline not green'}`)
    return
  }
  ;(r.mut.results || []).forEach((res) => {
    if (res.outcome === 'CAUGHT') return caught.push(res)
    if (res.outcome === 'DID_NOT_RUN') return didNotRun.push(res)
    const v = r.verdicts.find((x) => x.anchor === res.anchor)
    if (!v) return didNotRun.push({ ...res, evidence: `${res.evidence} — UNCONFIRMED: no confirmer verdict` })
    if (!v.confirmed_unnoticed) return caught.push({ ...res, caught_by: v.caught_by || v.reason })
    decoration.push({ ...res, blast_radius: v.blast_radius || 'medium', confirmer_note: v.reason })
  })
})
decoration.sort((a, b) => rank(a.blast_radius) - rank(b.blast_radius))
log(`${decoration.length} guard(s) confirmed unnoticed, ${caught.length} caught, ${didNotRun.length} did not run, ${abandoned.length} batch(es) abandoned`)

const dirty = ok
  .map((r) => ({ batch: r.batchNo, s: r.mut.final_git_status }))
  .filter((x) => x.s && x.s.trim() && x.s.trim() !== 'clean')

phase('Rank')
const report = await agent(
  `${HOUSE}

Write the guard efficacy report.

CONFIRMED DECORATION — a mutation that broke the guard, and a second agent independently reproduced
a green gate at the same test count in its own worktree:
${JSON.stringify(decoration, null, 2)}

CAUGHT — the guard is held by a test (includes claims the confirmer overturned):
${JSON.stringify(caught.map((c) => ({ guard: c.guard, anchor: c.anchor, caught_by: c.caught_by })), null, 2)}

DID NOT RUN — no conclusion is available about these guards:
${JSON.stringify(didNotRun.map((c) => ({ guard: c.guard, anchor: c.anchor, why: c.evidence })), null, 2)}

BATCHES ABANDONED FOR A NON-GREEN BASELINE (correctly produced no findings):
${abandoned.join('\n') || 'none'}

BATCHES THAT PRODUCED NOTHING: ${lost}
WORKTREES LEFT DIRTY: ${dirty.length ? JSON.stringify(dirty) : 'none'}

Write exactly this and nothing else:

1. HEADLINE — one line: N guards mutated, D confirmed unnoticed, C caught, U inconclusive.
   If D is 0 and C is high, say so plainly — "the guards in this surface are held" is a valuable
   result and this workflow should be able to return it.

2. DECORATION — numbered, worst blast radius first. Each in four lines:
     GUARD:    <what it refuses> — <file:line>
     MUTATION: <the exact edit that went unnoticed>
     GATE:     <command> — green, <test count> tests, both times, in two independent worktrees
     FIX:      <the narrowest test that would have caught it — name the file it belongs in>
   Do not soften these. A guard nothing notices losing is not "under-tested", it is not enforced.

3. INCONCLUSIVE — every DID_NOT_RUN and every abandoned batch, with the specific reason and the
   command that would make it runnable. This section is NOT a list of healthy guards. Say that.

4. HYGIENE — any worktree left dirty. If the list is empty, say "all worktrees clean".

Terse. No preamble, no emoji. Do not commit, push, merge or open a PR — the fixes belong to a
human, and every mutation in this run has been reverted.`,
  { label: 'guard efficacy report' },
)

return report
