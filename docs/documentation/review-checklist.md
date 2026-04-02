# Documentation Review Checklist

## Purpose

Use this checklist when reviewing PRs that include documentation changes, or when checking whether a code PR is missing doc updates.

---

## For Code PRs (Does This Need a Doc Update?)

- [ ] **Contracts changed?** → Update example payloads, update component docs that reference the contract
- [ ] **Component scope changed?** → Update `docs/components/<component>.md`
- [ ] **API added or changed?** → Update OpenAPI spec in `contracts/api/`
- [ ] **Event schema changed?** → Update schema in `contracts/events/`, update boundary contracts doc
- [ ] **Testing approach changed?** → Update `docs/testing/` or `docs/components/testing/`
- [ ] **Setup process changed?** → Update `docs/setup/`
- [ ] **Deployment or ops changed?** → Update relevant runbook, refresh `Last verified` date
- [ ] **Architecture decision made?** → Create ADR in `docs/adr/`
- [ ] **New component added?** → Create component doc using template, create testing guide

---

## For Documentation PRs

- [ ] **Describes current state, not future state** (unless clearly marked as planned)
- [ ] **References contract files rather than duplicating them**
- [ ] **All internal links are valid** (run `python scripts/check_doc_links.py`)
- [ ] **Component docs have required headings** (run `python scripts/check_component_docs.py`)
- [ ] **Runbooks have required metadata** (run `python scripts/check_runbooks.py`)
- [ ] **Mermaid diagrams validate** (run `npm run --silent check:mermaid`)
- [ ] **Markdown lint passes** (run `markdownlint <file> --config .markdownlint.json`)
- [ ] **Language is plain and direct** — avoid jargon, vague qualifiers, and passive voice
- [ ] **Examples are concrete** — show actual values, not "e.g., some value"
- [ ] **Tables are used for structured comparisons** — not long prose paragraphs

---

## Quick Check Commands

```bash
# Run all doc checks
./scripts/check_docs.sh

# Run specific checks
python scripts/check_doc_links.py
python scripts/check_component_docs.py
python scripts/check_runbooks.py
python scripts/check_diagram_format.py
npm run --silent check:mermaid
python scripts/validate_openapi.py
python scripts/validate_json_schemas.py
```
