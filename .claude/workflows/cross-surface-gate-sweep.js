// Cross-surface gate sweep — run every per-surface gate that a change actually touches, in
// parallel, and aggregate honestly.
//
// WHY THIS IS A WORKFLOW AND NOT A MAKEFILE. The hard part is not running the gates; it is
// refusing to call a gate that did not run a gate that passed. A shell script cannot make that
// judgement — `scripts/check-platform-control.sh` IS the shell script, and it still skips its
// entire admin half without comment when `admin/package.json` is absent
// (check-platform-control.sh:18, `if [[ -f admin/package.json ]]`). It hard-fails on missing
// node_modules now, which is the fix for one half of the worktree trap, but the outer
// `if` remains a silent skip. Distinguishing "green" from "never executed" needs a reader who
// knows what the output should have looked like.
//
// It is also why the sweep is STRUCTURED rather than one big `&`: gates that rewrite tracked
// files (contract and client regeneration) must not run while other gates diff the tree.
// docs/process/max-parallel-execution.md:44 — one owner per OpenAPI file — is a constraint on
// this workflow, not just on humans. So mutating gates are serialized after the parallel phase.
//
// Runs gates. Changes nothing else: no commit, no push, no merge, no PR comment.

export const meta = {
  name: 'cross-surface-gate-sweep',
  description:
    'Run every touched surface\'s CI-equivalent gate in parallel and report PASS / FAIL / DID-NOT-RUN as three distinct outcomes',
  whenToUse:
    'Before pushing a branch that spans surfaces, or when a "green" local run needs to be trusted. Not a substitute for CI — a substitute for guessing which gate CI will run.',
  phases: [
    { title: 'Select', detail: 'map the diff onto the CLAUDE.md gate table' },
    { title: 'Sweep', detail: 'one agent per read-only gate, in parallel' },
    { title: 'Serialize', detail: 'tree-mutating gates, one at a time, after the sweep' },
    { title: 'Aggregate', detail: 'honest ledger — DID-NOT-RUN never rounds up to PASS' },
  ],
}

const A = args || {}
const ALL = A.all === true // sweep every gate regardless of what changed
const BASE = A.base || 'origin/main'
// Hard ceiling on parallel gate agents. Default keeps a full run at ≤15 agents.
const MAX_GATES = A.maxGates || 12

// The gate table. Source of truth is CLAUDE.md "Per-surface quality gates"; this mirrors it, and
// the Select agent is told to re-read CLAUDE.md and report any disagreement rather than trusting
// this list. `mutates: true` means the gate rewrites TRACKED files (generate-then-diff), so it
// cannot run beside a gate that reads the tree.
const GATES = [
  {
    id: 'platform-control',
    paths: ['platform-control/'],
    cmd: 'bash scripts/check-platform-control.sh',
    notes:
      'ruff check + ruff format --check + pytest + the OpenAPI contract-drift gate + the full admin gate. A bare `uv run pytest` is NARROWER than CI. The admin half is wrapped in `if [[ -f admin/package.json ]]` (check-platform-control.sh:18) — if that file is absent the admin half is SKIPPED SILENTLY and the script still exits 0. Check the output for the admin section; if it is missing, this is DID_NOT_RUN for the admin half.',
  },
  {
    id: 'platform-control-admin',
    paths: ['platform-control/admin/'],
    cmd: 'cd platform-control/admin && npm run check && npm run build',
    notes: 'Needs node_modules IN THIS CHECKOUT — a git worktree does not inherit them. Needs Node 22.',
  },
  {
    id: 'document-intelligence',
    paths: ['document-intelligence/'],
    cmd: 'cd document-intelligence && uv run --extra dev --extra service --extra test --extra llm pytest && uv run ruff check . && uv run ruff format --check .',
    notes:
      'The extras are NOT optional. Without them test_instructor_extractor and test_eval_docling_extractor cannot be collected, and without --extra llm test_dspy_modules.py (11 tests) is dropped at COLLECTION and the eval harness skips — a green run over a smaller suite than CI. If you see fewer tests than expected, that is DID_NOT_RUN, not PASS.',
  },
  {
    id: 'legal-search-api',
    paths: ['legal-search/api/'],
    cmd: 'cd legal-search/api && npm run check',
    notes:
      'Includes the integration layer (*.integration.spec.ts, via npm run test:integration), which needs a RUNNING DOCKER DAEMON — it is the only layer that meets a real index mapping (#672/#673/#675). Also includes npm run test:compiled, the only layer that can see a NestJS controller DTO erased by `import type` (#728) — Vitest emits no decorator metadata and cannot. If Docker is absent, report the integration layer as DID_NOT_RUN even when the rest is green.',
  },
  {
    id: 'legal-search-frontend',
    paths: ['legal-search/frontend/'],
    cmd: 'cd legal-search/frontend && npm run check && npm run build',
    notes: 'The build is a SEPARATE CI step and catches SSR issues tsc misses. Needs Node 22.',
  },
  {
    id: 'marketing',
    paths: ['marketing/'],
    cmd: 'cd marketing && npm run check && npm run build',
    notes: 'The static export is the deploy artifact, so the build is part of the gate.',
  },
  {
    id: 'evidara-cli',
    paths: ['tools/evidara-cli/'],
    cmd: 'bash scripts/check-evidara-cli.sh',
  },
  {
    id: 'scripts',
    paths: ['scripts/'],
    cmd: 'uv run --with pyyaml python -m unittest discover -s scripts/tests -p "test_*.py"',
    notes:
      '`--with pyyaml` is NOT optional. Without it seven modules fail to import and the runner says "Ran 97 tests ... FAILED (errors=7)" — which reads as seven broken tests and is really THIRTY-SEVEN THAT NEVER RAN. If the total is 97, this is DID_NOT_RUN.',
  },
  {
    id: 'country-overlays',
    paths: ['country-overlays/', 'platform-control/src/platform_control/seeds/'],
    cmd: 'python scripts/check_country_overlay_files.py',
  },
  {
    id: 'scraping-qa',
    paths: ['__ANY_SCRAPING__'],
    cmd: 'bash scripts/check-scraping-qa.sh',
    notes: 'Applies to any PR that touches scraping, wherever it lives — judge from the diff, not from a path prefix.',
  },
  {
    id: 'js-workspace-hygiene',
    paths: ['legal-search/', 'platform-control/admin/', 'marketing/', 'styles/', 'package.json', '.nvmrc'],
    cmd: 'bash scripts/check-js-workspace-hygiene.sh',
    notes: 'Also fails if your Node major does not match .nvmrc — which is itself the signal that every other JS gate in this sweep is untrustworthy.',
  },
  {
    id: 'e2e-spec-coverage',
    paths: ['legal-search/frontend/e2e/'],
    cmd: 'bash scripts/check-e2e-spec-coverage.sh',
    notes: 'Asserts every spec is selected by some CI command (#686) — a spec no command runs is a test that cannot fail.',
  },
  { id: 'docs', paths: ['docs/', 'contracts/'], cmd: 'bash scripts/check_docs.sh' },
  { id: 'architecture', paths: ['structurizr/'], cmd: 'bash scripts/check-architecture.sh' },
  { id: 'shellcheck', paths: ['scripts/', '.github/'], cmd: 'bash scripts/check-shellcheck.sh' },
]

// Gates that regenerate tracked artifacts. They are serialized AFTER the parallel phase because
// they rewrite files other gates are diffing, and because the OpenAPI file is single-owner.
const MUTATING = [
  {
    id: 'frontend-openapi-drift',
    paths: ['contracts/api/', 'legal-search/frontend/'],
    cmd: 'cd legal-search/frontend && npm run openapi:check',
    notes: 'Generate-then-diff: it REWRITES the generated client. Never run beside a gate that reads the tree. Revert any regenerated file you did not intend to keep.',
  },
]

const HOUSE = `
GROUND RULES (.claude/workflows/_house-rules.md):

NODE. CI pins Node 22 (.nvmrc). Source it with SEMICOLONS, not && — nvm.sh returns exit 3 and
short-circuits an && chain:
    export NVM_DIR="$HOME/.config/nvm"; . "$NVM_DIR/nvm.sh"; nvm use 22; node -v
"ExperimentalWarning: localStorage is not available" in gate output means you are on the WRONG Node
and every JS result you have is dishonest. Report that as DID_NOT_RUN.

THREE OUTCOMES, NEVER TWO.
  PASS        — the gate ran to completion and exited 0. You saw its real output.
  FAIL        — the gate ran and exited non-zero. Paste the failing assertion.
  DID_NOT_RUN — anything else. Missing toolchain, missing node_modules, no Docker daemon, wrong
                Node, a sub-step skipped by an outer shell conditional, a collection error, a suite
                that ran far fewer tests than it should. A gate that fell over in setup DID NOT PASS.
Exit code 0 is NOT sufficient evidence of PASS. Read the output and check the gate did the work.

EVIDENCE. Paste the last ~15 lines of real output, verbatim, for every outcome including PASS.
Include the test counts. If you cannot paste real output you do not have a result.

BOUNDARY. Do not commit, push, merge, comment on a PR, or delete a branch. Do not contact any
public-sector host. Do not dispatch an acquisition run. Do not flip a config key.

TREE. If a gate rewrote a tracked file, say which, and \`git status --short\` at the end so the
caller can see what the sweep left behind.
`

const GATE_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['gate', 'command', 'outcome', 'evidence'],
  properties: {
    gate: { type: 'string' },
    command: { type: 'string' },
    outcome: { type: 'string', enum: ['PASS', 'FAIL', 'DID_NOT_RUN'] },
    evidence: { type: 'string', description: 'Real output tail, verbatim. Required for every outcome.' },
    reason: { type: 'string', description: 'For DID_NOT_RUN / FAIL: what stopped it, specifically.' },
    counts: { type: 'string', description: 'Tests collected/run/skipped, if the gate reports them.' },
    tree_dirty: { type: 'string', description: 'git status --short after the gate, or "clean".' },
  },
}

function runGate(g, phaseName) {
  return agent(
    `${HOUSE}

Run exactly one gate and report what really happened.

GATE: ${g.id}
COMMAND (run it from the repo root, verbatim):
    ${g.cmd}
${g.notes ? `\nKNOWN TRAPS FOR THIS GATE — check for each one before you claim PASS:\n${g.notes}\n` : ''}
Run it. Read the output. Then classify it as PASS / FAIL / DID_NOT_RUN using the three-outcome rule
above, and paste the real tail. If the gate has sub-steps and one of them was skipped, the gate is
DID_NOT_RUN for that sub-step — say which, and report the overall outcome as DID_NOT_RUN unless
every sub-step demonstrably ran.

Do not fix anything you find. Do not retry with a narrower command to get a green — if the CI
command cannot run here, that IS the result.`,
    { phase: phaseName, label: g.id, schema: GATE_SCHEMA },
  )
}

// ── run ──────────────────────────────────────────────────────────────────────
phase('Select')

const selection = await agent(
  `${HOUSE}

Decide which gates this change needs.

1. Get the changed paths: \`git diff --name-only ${BASE}...HEAD\` and \`git status --short\`.
   ${ALL ? 'args.all was set — you must select EVERY gate regardless of the diff, but still report the diff.' : ''}
2. RE-READ CLAUDE.md's "Per-surface quality gates" table. It is the source of truth. Compare it
   against this candidate list and REPORT ANY DISAGREEMENT — the list may have rotted:
${GATES.map((g) => `     - ${g.id}: ${g.cmd}`).join('\n')}
${MUTATING.map((g) => `     - ${g.id} (tree-mutating): ${g.cmd}`).join('\n')}
   Note: .claude/commands/merge-readiness.md carries an OLDER, NARROWER gate table (it says
   "cd platform-control && uv run pytest", which CLAUDE.md explicitly calls narrower than CI).
   If you saw that, say so — do not use it.
3. Report the environment, because it decides what CAN run: \`node -v\` after sourcing nvm, whether
   \`uv\` is on PATH, whether a Docker daemon is reachable (\`docker info\`), and whether
   platform-control/admin/node_modules, legal-search/api/node_modules,
   legal-search/frontend/node_modules and marketing/node_modules exist IN THIS CHECKOUT.
   A missing one means that gate will be DID_NOT_RUN — say so up front rather than discovering it.
4. Judge whether any part of the diff is scraping-adjacent (provider code, acquisition specs,
   compliance policies, host allow-lists, robots handling). That gate is judged from content, not
   from a path prefix.

Return ONLY a JSON object:
  {"gates": ["<id>", ...], "mutating": ["<id>", ...], "changed_paths": [...],
   "env": {"node": "...", "uv": true/false, "docker": true/false, "node_modules_missing": [...]},
   "table_disagreements": ["..."]}
Ids must come from the candidate list above.`,
  { label: 'select gates' },
)

let sel = { gates: [], mutating: [], env: {}, table_disagreements: [] }
try {
  const m = String(selection).match(/\{[\s\S]*\}/)
  if (m) sel = { ...sel, ...JSON.parse(m[0]) }
} catch (e) {
  log('⚠ could not parse the gate selection — falling back to the full sweep')
}
if (ALL || !sel.gates || sel.gates.length === 0) {
  sel.gates = GATES.map((g) => g.id)
  sel.mutating = MUTATING.map((g) => g.id)
}
if (sel.table_disagreements && sel.table_disagreements.length) {
  log(`⚠ gate table disagrees with CLAUDE.md: ${sel.table_disagreements.join('; ')}`)
}

let chosen = GATES.filter((g) => sel.gates.indexOf(g.id) !== -1)
if (chosen.length > MAX_GATES) {
  const dropped = chosen.slice(MAX_GATES).map((g) => g.id)
  log(`⚠ CAPPED at maxGates=${MAX_GATES}. NOT RUN, and therefore NOT PASSED: ${dropped.join(', ')}`)
  chosen = chosen.slice(0, MAX_GATES)
}
const chosenMutating = MUTATING.filter((g) => (sel.mutating || []).indexOf(g.id) !== -1)
log(`${chosen.length} parallel gate(s), ${chosenMutating.length} serialized; ~${chosen.length + chosenMutating.length + 2} agents`)

phase('Sweep')
const swept = await parallel(chosen.map((g) => () => runGate(g, 'Sweep')))

// Serialized, one at a time: these rewrite tracked files and the OpenAPI file is single-owner
// (docs/process/max-parallel-execution.md:44).
const mutated = []
if (chosenMutating.length) {
  phase('Serialize')
  for (const g of chosenMutating) {
    mutated.push(await runGate(g, 'Serialize'))
  }
}

const results = swept.concat(mutated)
const lost = chosen.length + chosenMutating.length - results.filter(Boolean).length
if (lost > 0) log(`⚠ ${lost} gate agent(s) returned nothing — those gates are UNKNOWN, not green`)

const ledger = results.filter(Boolean)
const cappedOut = GATES.filter((g) => sel.gates.indexOf(g.id) !== -1).slice(MAX_GATES).map((g) => g.id)

phase('Aggregate')
const report = await agent(
  `${HOUSE}

Write the gate ledger. You are the last honest step; do not improve the news.

RESULTS:
${JSON.stringify(ledger, null, 2)}

ENVIRONMENT AS OBSERVED AT SELECTION TIME:
${JSON.stringify(sel.env || {}, null, 2)}

GATE AGENTS THAT RETURNED NOTHING AT ALL: ${lost}
GATES DROPPED BY THE maxGates CAP (not run, not passed): ${cappedOut.length ? cappedOut.join(', ') : 'none'}
CLAUDE.md TABLE DISAGREEMENTS REPORTED: ${(sel.table_disagreements || []).join('; ') || 'none'}

Write exactly this and nothing else:

1. HEADLINE — one line, one of:
     ALL GREEN            (every selected gate PASS, none DID_NOT_RUN, none dropped, none lost)
     RED                  (any FAIL)
     INCOMPLETE           (any DID_NOT_RUN, dropped, or lost agent, and no FAIL)
   INCOMPLETE is NOT a pass. Never write ALL GREEN when a gate did not run. This line is the whole
   point of the workflow.

2. LEDGER — a markdown table: gate | command | PASS/FAIL/DID_NOT_RUN | test counts | evidence
   (one line). Every selected gate gets a row, including dropped and lost ones — those get
   DID_NOT_RUN with the reason "capped by maxGates" or "agent returned nothing".

3. FAILURES — for each FAIL: the failing assertion, verbatim, and the file it points at.

4. WHY GATES DID NOT RUN — for each DID_NOT_RUN: the specific cause and the exact command that
   would fix it (e.g. \`(cd platform-control/admin && nvm use && npm ci)\`, \`start the Docker
   daemon\`, \`nvm use 22\`). Do not merge these into the failures section.

5. TREE STATE — anything the sweep left dirty, from the tree_dirty fields. If a mutating gate
   regenerated a tracked file, say which and whether it should be committed or reverted.

Terse. No preamble, no emoji, no encouragement. Do not commit, push or open a PR.`,
  { label: 'gate ledger' },
)

return report
