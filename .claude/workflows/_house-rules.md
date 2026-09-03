# House rules — shared by every `.claude/workflows/*.js` script

This file is documentation only. It is **not** imported by the scripts: Workflow scripts run
without filesystem or module access, so each script inlines its own `HOUSE` string. When you
change a rule here, change it in the scripts too — the same "add a check to one, add it to the
other" rule `AGENTS.md` applies to pre-commit and CI.

## 1. Never trust a reported result

A gate result you did not produce is a claim, not evidence. CI green, a PR body, a code comment,
an ADR, an issue title and **another agent's report** are all claims. Re-run the gate yourself and
paste the real tail of its output.

This is the rule the whole catalogue exists for. Every finding that mattered in this repo's
history was found by re-deriving a claim, never by reading a diff.

## 2. `DID-NOT-RUN` is not `PASS`

A gate that fell over during setup did not pass. The known ways a gate reads green while running
nothing:

| Trap | Signature |
|---|---|
| Wrong Node | `ExperimentalWarning: localStorage is not available`. CI pins Node 22 (`.nvmrc`); the workstation default is newer. Source it with **semicolons**, not `&&` — `nvm.sh` returns 3 and short-circuits an `&&` chain: `export NVM_DIR="$HOME/.config/nvm"; . "$NVM_DIR/nvm.sh"; nvm use 22` |
| Missing `pyyaml` | `scripts/` reports `Ran 144 tests ... FAILED (errors=11)` instead of the real 201. That is **57 tests that never ran**, not 11 that broke. Use `uv run --with pyyaml python -m unittest discover -s scripts/tests -p "test_*.py"` |
| Missing DI extras | `document-intelligence` silently drops `test_dspy_modules.py` and skips the eval harness. Use `uv run --extra dev --extra service --extra test --extra llm pytest` |
| No Docker daemon | `legal-search/api` integration layer (`*.integration.spec.ts`) is the only layer that meets a real index mapping. Without Docker it does not run |
| A skipped sub-step | `scripts/check-platform-control.sh` wraps its whole admin half in `if [[ -f admin/package.json ]]` (`:18`). If that file is absent the admin half is skipped **silently** and the script still exits 0. Read the output for the admin section rather than trusting the exit code. **Not** a trap: missing `platform-control/admin/node_modules` in a fresh worktree — `:36-42` (added by #687) detects that, prints the checkout path and the exact `npm ci` remedy, and exits non-zero |

Report the outcome as one of `PASS` / `FAIL` / `DID_NOT_RUN`, never collapse the third into the
first, and always carry the reason.

## 3. Evidence or silence

Every finding must be anchored to something a sceptic can re-derive without trusting you:

- a `file:line`, quoted;
- a number you measured, with the command that produced it;
- a behaviour you reproduced, with the invocation;
- a mutation you applied that did **not** turn a test red.

A finding whose only support is an opinion ("consider extracting a helper", "improve error
handling", "add more tests") is dropped by construction. This repo's culture is evidence or
silence, and a wishlist is worse than an empty report because it costs a human the read.

## 4. Refute, don't confirm

The verify stage's job is to **kill** the finding. Verifiers default to `refuted: true` when they
cannot re-derive the claim themselves. Absence of proof is refutation here, not a tie.

## 5. Rank and cap

Output the top findings by blast radius, not everything found. A 40-item list is ignored; a
5-item list with reproductions gets fixed. When a cap drops something, `log()` what was dropped —
a silent truncation reads as "covered everything" when it did not.

## 6. The boundary these workflows must not cross

None of these scripts may:

- point a crawler, fetcher or browser at a **public-sector host**. LexFind's terms were never
  confirmed with the Schweizerische Staatsschreiberkonferenz, and the cantonal portals are not
  ours to load;
- **dispatch an acquisition run** in any mode;
- **flip a config key** — `enabled: true` on a blueprint template is the operator's act under
  ADR-0030, and a provider's `readiness` is the code key. Neither is an agent's to turn;
- **merge a PR, push to `main`, delete a branch, or comment on a PR**;
- build the MCP server or anything shaped like it (ADR-0033 §4).

A workflow that reaches one of these boundaries **stops and emits a decision memo** naming what a
human must decide. The memo is the deliverable; the action is not.

## 7. Serialization — inherited from `docs/process/`

These are constraints on what may fan out, not suggestions:

- **One owner per OpenAPI file** (`docs/process/max-parallel-execution.md:44`). Only one agent in
  a run may regenerate `contracts/api/platform-control.openapi.yaml`.
- **One owner per Alembic migration batch** (`:45`). No workflow authors a migration.
- **Same GitHub Actions workflow file → expect conflicts** (`:46`). No workflow edits `.github/`.
- **Cross-service behaviour → contract or event schema first** (`:47`).

The practical consequence for these scripts: a stage that **mutates the working tree** must never
run concurrently with a stage that **reads** it. Where a script needs both, the mutating stage is
either serialized after the parallel read stage, or given `isolation: 'worktree'`.
