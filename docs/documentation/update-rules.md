# Documentation Update Rules

## Purpose

Define when and how documentation must be updated alongside code changes.

---

## Rule 1: Contract changes require doc updates in the same PR

If you change any file in:

- `contracts/api/`
- `contracts/schemas/`
- `contracts/events/`

You must also update:

- The corresponding example payload (if it exists)
- The component doc that references the contract (if the change is user-facing)
- The boundary contracts doc (`docs/architecture/boundary-contracts.md`) if the change affects a boundary

**Why:** Contracts are the most critical documentation. Stale contracts cause integration failures.

---

## Rule 2: Component behavior changes require component doc updates

If you change the scope, responsibilities, or boundaries of a component, update `docs/components/<component>.md`.

Specifically:

- New API endpoints → update "Responsibilities" or "Key Contracts"
- Changed state machines → update state transition documentation
- New dependencies → update "Dependencies" section
- Changed boundaries → update "Boundary" section

**Why:** Component docs are how new contributors (and AI tools) understand what a component does.

---

## Rule 3: Testing changes require testing doc updates

If you add, remove, or significantly change tests:

- Update the relevant component testing guide in `docs/components/testing/`
- Update `docs/testing/` if the change affects shared strategy (e.g., new CI check, new test level)

**Why:** Testing docs guide what tests to write next. If they don't match reality, they mislead.

---

## Rule 4: Runbook procedures must be verified when changed

If you change deployment, operations, or recovery procedures:

- Update the relevant runbook in `docs/runbooks/`
- Update `Last verified` date after confirming the procedure works
- Update `Last reviewed` date if you reviewed but did not verify

**Why:** Stale runbooks cause incidents. A runbook with an old `Last verified` date signals low confidence.

---

## Rule 5: Architecture decisions require ADRs

If you make a decision that:

- Changes how components communicate
- Changes storage or data ownership
- Adds or removes a dependency
- Changes the deployment model

Create an ADR in `docs/adr/`.

**Why:** ADRs document why decisions were made, not just what was decided. This prevents re-litigating settled decisions.

---

## Rule 6: Do not describe future state as current state

Documentation must describe what exists now. If you want to document a planned feature:

- Use a clear marker like `## Planned` or `## Future`
- Or create a separate planning document
- Never mix future-state descriptions with current-state documentation without a label

**Why:** Readers (especially AI tools) cannot distinguish "this exists" from "we want this to exist" unless it is marked.

---

## Rule 7: Docs can follow code, but not by more than one PR

It is acceptable for code to land slightly ahead of documentation. But:

- The doc update should be in the same PR when possible
- If not, it must be in the immediately following PR
- Never let docs lag by more than one PR

**Why:** The longer the gap, the more likely the update is forgotten.

---

## MkDocs build directory (`site/`)

A local **`site/`** directory at the repo root is **generated output** from `mkdocs build` (including `scripts/check_docs.sh`). It is **not source** and must **not** be committed (see `.gitignore`). Remove stray copies with `rm -rf site/` if you want a clean working tree.

---

## Enforcement

| Rule                       | Enforced by                                     |
| -------------------------- | ----------------------------------------------- |
| Contract + example updates | CI (schema validation fails on stale examples)  |
| Component doc headings     | Pre-commit (heading checker)                    |
| Runbook metadata           | Pre-commit (metadata checker)                   |
| Doc link validity          | Pre-commit (link checker)                       |
| Behavior and scope updates | AI PR review (advisory)                         |
| ADR creation               | Manual (PR review)                              |
| No future-as-current       | AI PR review (advisory)                         |
