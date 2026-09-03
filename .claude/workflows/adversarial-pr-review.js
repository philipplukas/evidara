// Adversarial PR review — re-derive the claim, do not read the diff.
//
// The repo already has `/code-review` (the official plugin command). This workflow does NOT
// duplicate it. `/code-review` is a *diff-reading* review: five agents read the diff, git blame,
// prior PR comments and code comments, then a confidence scorer drops anything under 80. Its own
// instructions say "Do not check build signal or attempt to build or typecheck the app" and list
// "lack of test coverage" among its false positives.
//
// Every finding that mattered in this repo's history sat exactly in that blind spot:
//   - a feature that could be deleted entirely with all 286 tests still passing;
//   - a deny-assertion that probed a nonexistent key and therefore could never fail;
//   - an operator kill-switch that could be flipped with exit 0;
//   - a change that would have duplicated the federal corpus at every future consolidation.
// None is visible in a diff. All four are visible the moment you run something.
//
// So: `/code-review` reads. This one runs. Use both.
//
// Refuses to: comment on the PR, merge it, push, or delete a branch. It returns a report.

export const meta = {
  name: 'adversarial-pr-review',
  description:
    'Review a change by re-running its gates and mutation-testing its tests, not by reading the diff',
  whenToUse:
    'Before merging a PR that touches behaviour, contracts or guards — especially one whose own CI is green. Complements /code-review, which reads the diff and explicitly does not build or run anything.',
  phases: [
    { title: 'Scope', detail: 'resolve the target, changed surfaces, and the claims it makes' },
    { title: 'Interrogate', detail: 'one finder per review dimension, each re-deriving by execution' },
    { title: 'Refute', detail: 'an independent sceptic per dimension tries to kill every finding' },
    { title: 'Decide', detail: 'rank survivors by blast radius and write the merge verdict' },
  ],
}

// ── knobs ────────────────────────────────────────────────────────────────────
const A = args || {}
// What to review. A PR number, a branch, a path, or the default working-tree diff.
const TARGET = A.target || 'the working-tree diff against origin/main'
// Sceptics per dimension. Default 1 keeps a full run at 12 agents (under the medium cap of 15).
// Raise to 2 for a 17-agent pass, 3 for 22. Each sceptic re-derives EVERY finding of its dimension,
// so raising this buys independence, not coverage — no finding is ever dropped by this number.
const VERIFY_FANOUT = Math.max(1, Math.min(3, A.verifyFanout || 1))
// Findings carried into the verdict. Rank-and-cap: a 40-item list is ignored.
const TOP_N = A.topN || 8

const HOUSE = `
GROUND RULES (.claude/workflows/_house-rules.md — these override your instincts):

1. NEVER TRUST A REPORTED RESULT. CI green, the PR body, a code comment, an ADR, an issue title
   and any other agent's report are CLAIMS, not evidence. Re-run the gate yourself and paste the
   real tail of its output. This rule is why this workflow exists.

2. DID-NOT-RUN IS NOT PASS. Known ways a gate reads green while running nothing:
   - Wrong Node. CI pins 22 (.nvmrc); the workstation default is newer and makes vitest dishonest.
     Source it with SEMICOLONS, not && (nvm.sh returns 3 and short-circuits an && chain):
       export NVM_DIR="$HOME/.config/nvm"; . "$NVM_DIR/nvm.sh"; nvm use 22
     "ExperimentalWarning: localStorage is not available" means you are on the wrong Node.
   - scripts/ without pyyaml reports "Ran 144 tests ... FAILED (errors=11)" instead of the real 201.
     That is 57 tests that NEVER RAN, not 11 that broke. Use:
       uv run --with pyyaml python -m unittest discover -s scripts/tests -p "test_*.py"
   - document-intelligence without extras silently drops test_dspy_modules.py. Use:
       cd document-intelligence && uv run --extra dev --extra service --extra test --extra llm pytest
   - legal-search/api's *.integration.spec.ts layer needs a running Docker daemon.
   - scripts/check-platform-control.sh wraps its ENTIRE admin half in
     \`if [[ -f admin/package.json ]]\` (check-platform-control.sh:18). If that file is absent the
     admin half is skipped SILENTLY and the script still exits 0 — read the output for the admin
     section instead of trusting the exit code.
     Do NOT assume the related worktree case: missing platform-control/admin/node_modules is
     DETECTED at :36-42, which prints the checkout path and the exact \`npm ci\` remedy and exits
     non-zero. That one fails loudly; do not report it as a silent pass.
   If a gate could not run, say DID_NOT_RUN and why. Never collapse it into PASS.

3. EVIDENCE OR SILENCE. Every finding is anchored to a quoted file:line, a number with the command
   that produced it, a reproduction with its invocation, or a mutation that did not turn a test red.
   "Consider extracting a helper" / "improve error handling" / "add more tests" are dropped by
   construction. A wishlist is worse than an empty report.

4. BOUNDARY. Do not fetch from any public-sector host, dispatch an acquisition run in any mode,
   flip a blueprint template's \`enabled\` key or a provider's \`readiness\`, merge, push, comment on
   a PR, or delete a branch. If your finding needs one of those to confirm, report it as
   NEEDS-HUMAN-DECISION with the exact command a human would run.

5. LEAVE THE TREE AS YOU FOUND IT. If you mutate a file to test something, revert it (git checkout
   -- <path>) and say so. Never leave a mutation behind. Never regenerate
   contracts/api/platform-control.openapi.yaml unless you are the contract-sync dimension — it is a
   single-owner artifact (docs/process/max-parallel-execution.md:44).
`

const FINDINGS_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['dimension', 'gates_run', 'findings'],
  properties: {
    dimension: { type: 'string' },
    gates_run: {
      type: 'array',
      description: 'Every gate/command you actually executed, with its real outcome.',
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['command', 'outcome'],
        properties: {
          command: { type: 'string' },
          outcome: { type: 'string', enum: ['PASS', 'FAIL', 'DID_NOT_RUN'] },
          evidence: { type: 'string', description: 'Tail of real output, or why it did not run.' },
        },
      },
    },
    findings: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['title', 'anchor', 'how_derived', 'blast_radius'],
        properties: {
          title: { type: 'string' },
          anchor: { type: 'string', description: 'file:line, quoted. Required.' },
          how_derived: {
            type: 'string',
            description: 'The exact command or mutation that produced this, and its output.',
          },
          blast_radius: { type: 'string', enum: ['ship-blocker', 'high', 'medium', 'low'] },
          suggested_fix: { type: 'string' },
        },
      },
    },
    dropped: { type: 'string', description: 'What you looked at and deliberately did not report.' },
  },
}

const VERDICT_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['verdicts'],
  properties: {
    verdicts: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['title', 'refuted', 'reason'],
        properties: {
          title: { type: 'string' },
          refuted: { type: 'boolean' },
          reason: { type: 'string', description: 'What you re-derived, and the command you ran.' },
          corrected_anchor: { type: 'string' },
          severity_after_check: { type: 'string', enum: ['ship-blocker', 'high', 'medium', 'low', 'none'] },
        },
      },
    },
  },
}

// Worst-first. Declared here, not below the pipeline: the refute stage closes over it and runs
// before any later statement would have initialised it.
const SEVERITY = ['ship-blocker', 'high', 'medium', 'low', 'none']
// Sort key for blast radius. `indexOf` returns -1 for a missing or unrecognised value, which
// would sort an unlabelled finding ABOVE a ship-blocker; 99 puts it last instead.
const rank = (s) => (SEVERITY.indexOf(s) + 1 || 99)

// ── the five dimensions ──────────────────────────────────────────────────────
// Each is grounded in a real failure this repo shipped or nearly shipped.
const DIMENSIONS = [
  {
    id: 'correctness-by-re-derivation',
    ask: `Re-derive the change's central claim from the code, ignoring the PR body entirely.
Read what the code now does, then ask: does that produce the stated outcome, once, for every input?

Grounding — a change here would have duplicated the entire federal corpus and minted another copy
at every future consolidation, because nothing keyed identity on the thing that was actually
stable. So specifically hunt: identity/dedup keys, idempotency of anything that writes or seeds,
what happens on the SECOND run, and off-by-one on temporal boundaries (this repo has a live
inclusive-vs-exclusive contradiction on in_force_until between a producer and its consumer — see
lexfind_api_provider.py is_in_force vs legal-search/api/src/core/norm-hierarchy/in-force.ts).
Run the narrowest gate for the touched surface and paste its tail.`,
  },
  {
    id: 'tests-that-cannot-fail',
    ask: `MUTATION-TEST THE TESTS. Do not read them for quality — break the code and see if they notice.

For each test added or changed by this diff:
  a. Find the production code it claims to cover.
  b. Break that code in the most obvious way: delete the function body, invert the predicate,
     return a constant, remove the guard, or delete the feature outright.
  c. Re-run the narrowest gate. If it is still green, THAT is the finding.
  d. git checkout -- <path> to revert. Always. Say that you did.

Also check every assertion for whether it can fail at all: does it probe a key/field/path that
actually exists? Assert on a value that is ever different? A deny-assertion against a nonexistent
key passes forever and proves nothing.

Grounding — this exact technique found, on green PRs: a feature deletable with all 286 tests still
passing; a deny-assertion probing a key that did not exist; an operator kill-switch that could be
flipped with exit 0. Also: Vitest emits no decorator metadata, so a NestJS controller DTO bug is
invisible to every Vitest layer and only \`npm run test:compiled\` sees it (#728).`,
  },
  {
    id: 'contract-sync',
    ask: `You are the SINGLE OWNER of contract regeneration in this run. No other agent may touch it.

contracts/api/platform-control.openapi.yaml is GENERATED from the FastAPI app (ADR-0034), not
hand-written. If platform-control changed: regenerate and diff. Hand-maintaining it is what drifted
it to 4 of 11 acquisition providers (#614/#616/#618).

Then check the other single-source-of-truth artifacts the diff may have forked:
  - legal-search/api/src/core/opensearch/documents-index.mapping.ts is the ONE mapping source.
    Every producer derives from it; a second creation path does not disagree, it silently WINS
    (first-writer-wins). Drifted copies caused #675 and #713. Is any new producer in the PRODUCERS
    registry in mapping-drift.integration.spec.ts?
  - contracts/schemas/*.json, contracts/events/*.json, contracts/manifest.yaml.
  - Orval clients in legal-search/frontend (npm run openapi:check is the drift gate).
Run the drift gates. Paste real output. A contract change with no spec change is a finding.`,
  },
  {
    id: 'docs-vs-code-drift',
    ask: `Every factual claim in the docs, comments and docstrings this diff touches — and in the ones
it makes stale — must be re-derived against the code. Do not accept prose because it is adjacent
to the code it describes.

Recompute every NUMBER (counts of templates, providers, tests, cantons, routes) with a command,
and paste the command. Re-resolve every file:line citation — line numbers rot silently.

Grounding — comments in this repo have outranked the code they describe: canton_http's header still
said "ships DISABLED (live_ready=False)" while the class declared readiness = SCAFFOLD;
legifrance's said "Set live_ready = True once credentials are available", a no-op since readiness
wins; a comment claimed live_ready was "gone" when it is still honoured at
acquisition_core/providers.py:175. Two docs PRs corrected six false claims and a fact-checker still
found a wrong template count in one of them. Report only FALSIFIED claims, with the correct value.`,
  },
  {
    id: 'scope-discipline',
    ask: `Does the diff do only what it says, and everything it must?

  - Behaviour changed but no test changed → finding (AGENTS.md review guidance).
  - Terraform changed but docs not regenerated; architecture boundary crossed but
    structurizr/workspace.dsl and an ADR not updated → finding.
  - A new parallel abstraction where the repo already has one (AGENTS.md rule 2: grep before you
    create; rule 3: edit over duplicate) → finding, and name the existing abstraction.
  - Design tokens hardcoded instead of var(--token) → finding.
  - Hand-written OpenAPI client instead of a generated one → finding.
  - Did it silently claim an ADR number, a contracts/manifest.yaml version or a new file path that
    an OPEN PR already claims? Check in-flight PRs (gh pr list), not just main.
  - Did it cross a serialization seam it does not own — the same OpenAPI file, the same Alembic
    migration batch, the same GitHub Actions workflow file
    (docs/process/max-parallel-execution.md:44-47)?
Also: is anything in the diff dead on arrival — a field with no producer, a config knob with no
reader, an export with no consumer? A declared-and-empty field reads as "none exists".`,
  },
]

// ── run ──────────────────────────────────────────────────────────────────────
phase('Scope')
log(`Target: ${TARGET} — ${DIMENSIONS.length} dimensions, ${VERIFY_FANOUT} sceptic(s) each`)

const scope = await agent(
  `${HOUSE}

Scope a review of: ${TARGET}

Do NOT review anything yet. Produce the ground truth the reviewers will work from:
  1. The exact diff: changed files with +/- counts (gh pr diff <n> --name-only, or
     git diff --stat origin/main).
  2. Which surfaces are touched, and the CI-EQUIVALENT gate for each, from CLAUDE.md's
     "Per-surface quality gates" table. Quote the table rows you matched. Note that
     .claude/commands/merge-readiness.md carries an OLDER, NARROWER gate table (it says
     "cd platform-control && uv run pytest", which CLAUDE.md explicitly calls narrower than CI) —
     use CLAUDE.md, and say if you saw the two disagree.
  3. Every CLAIM the change makes: from the PR title/body, the commit messages, and any comment or
     docstring it adds. List them verbatim. These are what gets re-derived, and they are suspects,
     not facts.
  4. Which of the four serialization seams this change sits on, if any (OpenAPI file, Alembic
     migration batch, GitHub Actions workflow file, cross-service contract).
  5. Whether the working tree is clean, and the current git HEAD.
Return this as compact structured prose. Nothing else.`,
  { label: 'scope the change' },
)

const rounds = await pipeline(
  DIMENSIONS,

  // Stage 1 — find, by executing.
  (dim) =>
    agent(
      `${HOUSE}

You are the "${dim.id}" reviewer for: ${TARGET}

SCOPE (established by another agent — treat as a starting map, not as fact; re-check anything you
rely on):
${scope}

YOUR DIMENSION:
${dim.ask}

Work by running things, not by reading the diff. Report every gate you ran with its REAL outcome,
including DID_NOT_RUN. Report findings only where you can name the command or mutation that
produced them. If you found nothing, return an empty findings array — that is a good result, and
far better than padding. Use \`dropped\` to say what you examined and deliberately did not report.`,
      { phase: 'Interrogate', label: dim.id, schema: FINDINGS_SCHEMA },
    ),

  // Stage 2 — refute. Starts the moment THIS dimension reports; no barrier.
  async (found, dim) => {
    // A finder that died is NOT a clean dimension. Returning a tidy empty object here would make
    // rounds[i] truthy and hide the gap — this workflow's own "DID-NOT-RUN is not PASS" rule,
    // violated in its own code.
    if (!found) {
      log(`⚠ ${dim.id}: finder produced no result — this dimension was NOT covered`)
      return { dim: dim.id, gates: [], survivors: [], killed: 0, finderDied: true }
    }
    if (!found.findings || found.findings.length === 0) {
      return { dim: dim.id, gates: found.gates_run || [], survivors: [], killed: 0 }
    }
    const list = found.findings
      .map(
        (f, i) =>
          `[${i + 1}] ${f.title}\n    anchor: ${f.anchor}\n    claimed derivation: ${f.how_derived}\n    claimed severity: ${f.blast_radius}`,
      )
      .join('\n')

    const panels = await parallel(
      Array.from({ length: VERIFY_FANOUT }, (_, k) => () =>
        agent(
          `${HOUSE}

You are sceptic ${k + 1} of ${VERIFY_FANOUT} for the "${dim.id}" dimension on: ${TARGET}

YOUR JOB IS TO KILL THESE FINDINGS. You are not a second opinion; you are the defence.

${list}

For each one:
  - Re-derive it YOURSELF. Run the command again. Apply the mutation again. Open the file at the
    cited line and check the line number is still right — the citation may have rotted.
  - A finding survives only if you personally reproduced it. If you could not reproduce it, could
    not run the command, or the anchor does not say what the finder claims: refuted = true.
  - DEFAULT TO refuted = true WHEN UNCERTAIN. Absence of proof is refutation here, not a tie.
  - Also correct the severity. A finding can be real and still be low blast radius; say so.
  - Revert any mutation you make (git checkout -- <path>) and confirm you did.

Return one verdict per finding, in order.`,
          { phase: 'Refute', label: `refute ${dim.id} #${k + 1}`, schema: VERDICT_SCHEMA },
        ),
      ),
    )

    const votes = panels.filter(Boolean)
    if (votes.length === 0) {
      log(`⚠ ${dim.id}: every sceptic died — findings held UNVERIFIED, not confirmed`)
      return {
        dim: dim.id,
        gates: found.gates_run || [],
        survivors: found.findings.map((f) => ({ ...f, status: 'UNVERIFIED' })),
        killed: 0,
      }
    }

    const survivors = []
    let killed = 0
    found.findings.forEach((f, i) => {
      // Match on title first; fall back to position. The prompt asks for one verdict per finding
      // in order, but the schema cannot enforce that, and silently mis-pairing a verdict with a
      // finding would let a refuted claim survive under another finding's evidence.
      const forThis = votes
        .map((v) => {
          const list = v.verdicts || []
          return list.find((x) => x && x.title === f.title) || list[i]
        })
        .filter(Boolean)
      // No verdict at all is UNEXAMINED, not refuted. Killing on absence would delete a real
      // finding because a sceptic returned fewer verdicts than findings — the schema guarantees
      // neither the count nor the order.
      if (forThis.length === 0) {
        survivors.push({ ...f, status: 'UNVERIFIED — no sceptic verdict' })
        return
      }
      const refutes = forThis.filter((v) => v.refuted).length
      // Majority refutes → dead. A tie kills it too: the burden is on the finding.
      if (refutes * 2 >= forThis.length) {
        killed++
        return
      }
      const worst = forThis
        .map((v) => v.severity_after_check)
        .filter(Boolean)
        .sort((a, b) => rank(a) - rank(b))[0]
      survivors.push({
        ...f,
        status: 'SURVIVED',
        blast_radius: worst || f.blast_radius,
        anchor: (forThis.find((v) => v.corrected_anchor) || {}).corrected_anchor || f.anchor,
        refutation_notes: forThis.map((v) => v.reason).join(' | '),
      })
    })
    log(`${dim.id}: ${survivors.length} survived, ${killed} refuted`)
    return { dim: dim.id, gates: found.gates_run || [], survivors, killed }
  },
)

const ok = rounds.filter(Boolean)
const dead = DIMENSIONS.filter((d, i) => !rounds[i] || rounds[i].finderDied).map((d) => d.id)
if (dead.length) log(`⚠ dimensions that produced no result at all: ${dead.join(', ')}`)

const all = ok.flatMap((r) => r.survivors)
all.sort((a, b) => rank(a.blast_radius) - rank(b.blast_radius))
const top = all.slice(0, TOP_N)
if (all.length > top.length) {
  log(`capped at ${TOP_N}: dropped ${all.length - top.length} lower-blast-radius survivors`)
}

const gates = ok.flatMap((r) => r.gates)
const notRun = gates.filter((g) => g.outcome === 'DID_NOT_RUN')
const failed = gates.filter((g) => g.outcome === 'FAIL')

phase('Decide')
const verdict = await agent(
  `${HOUSE}

Write the merge verdict for: ${TARGET}

SURVIVING FINDINGS (each already re-derived by an independent sceptic; ${all.length} survived,
${ok.reduce((n, r) => n + r.killed, 0)} were refuted and are correctly absent):
${JSON.stringify(top, null, 2)}

GATES ACTUALLY EXECUTED DURING THIS REVIEW:
${JSON.stringify(gates, null, 2)}

DIMENSIONS THAT PRODUCED NOTHING (agent died or was skipped — coverage gap, not a clean bill):
${dead.length ? dead.join(', ') : 'none'}

Write, in this order and nothing else:

1. VERDICT — one of BLOCK / FIX-FIRST / SHIP. BLOCK if any surviving finding is ship-blocker, or if
   a gate for a touched surface is FAIL. FIX-FIRST if high-severity survivors exist.
   ${notRun.length ? `NOTE: ${notRun.length} gate(s) reported DID_NOT_RUN. A review with an unrun gate is not a clean review — say so in the verdict line, do not round it up to SHIP.` : ''}
   ${failed.length ? `NOTE: ${failed.length} gate(s) FAILED during this review.` : ''}
2. GATE LEDGER — a table: gate, command, PASS/FAIL/DID_NOT_RUN, evidence. DID_NOT_RUN rows must
   carry their reason. Do not omit them to make the table look better.
3. FINDINGS — one numbered entry each: title, anchor (file:line), how it was re-derived (the
   command), blast radius, suggested fix. Ordered by blast radius.
4. COVERAGE GAPS — what this review did NOT establish: dimensions that died, gates that did not
   run, anything marked NEEDS-HUMAN-DECISION, and anything the boundary rules stopped you from
   confirming.

Be terse. No preamble, no praise, no emoji. If there is nothing to report, say so in one line —
an empty finding list from a review that actually ran its gates is a real and useful result.
Do NOT post this anywhere: no gh pr comment, no merge, no push. It is returned to the caller.`,
  { label: 'merge verdict' },
)

return verdict
