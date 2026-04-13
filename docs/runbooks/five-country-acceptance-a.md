# Five-Country Acceptance A (CH + AT)

Owner: Platform / GA
Last reviewed: 2026-04-13
Last verified: 2026-04-13
Applies to: country slice 1-2 only

## Purpose

Define the acceptance lane for the first country slice of the five-country GA umbrella.
This lane covers Switzerland (CH) and Austria (AT) only and stays out of the DE / FR / IT
content-lane work so we can validate the shared model without overlap.

Canonical source context:

- [Five-Country Content Rollout](../components/five-country-content-rollout.md)
- [Platform-Control Multi-Country Operator Playbook](platform-control-multi-country-operator-playbook.md)
- [Metadata quality plan status](metadata-quality-plan-status.md)
- Linear umbrella: `TAR-160`

## Scope

In scope:

- CH and AT taxonomy mapping
- search filters and result labels
- subtitles, detail context, and metadata rows
- operator onboarding and triage evidence for CH / AT
- country-specific gap capture for this slice

Out of scope:

- DE / FR / IT overlays
- global glossary finalization
- branch-protection or release-policy changes
- full GA sign-off

## Shared acceptance checklist

### Taxonomy

- [ ] CH maps to the canonical keys in the shared taxonomy model.
- [ ] AT maps to the canonical keys in the shared taxonomy model.
- [ ] `jurisdiction`, `source_family`, `authority_type`, `court_level`, `language`, `official_only`, and `effective_date` resolve without country-specific ad hoc keys.
- [ ] No new CH/AT alias is introduced without a canonical mapping decision.
- [ ] Court-level and authority-type labels are stable across the two countries.

### Filters

- [ ] End-user filters use the same primary labels for CH and AT.
- [ ] Filter chips do not introduce country-specific wording for the same meaning.
- [ ] Helper text explains differences in legal structure instead of changing the primary label.
- [ ] Filter behavior matches the canonical keys in the five-country rollout doc.

### Subtitles and detail behavior

- [ ] Search results show a non-placeholder title for agreed CH / AT fixtures.
- [ ] Result subtitles follow the shared subtitle rules from the metadata acceptance plan.
- [ ] Detail view surfaces the expected metadata rows for citation, language, authority, and status when present.
- [ ] Controlled document types appear as controlled vocabulary labels, not `unknown`.
- [ ] Country-specific naming does not override canonical detail semantics.

### Operator flow evidence

- [ ] The country overlay can be selected in the operator playbook flow.
- [ ] Source onboarding follows the shared runbook flow.
- [ ] Preview or production run evidence is captured for both countries.
- [ ] Triage evidence shows the country-specific mapping checks and fallback actions.
- [ ] The operator checklist can be executed end-to-end for CH and AT.

### Country-specific gap capture

- [ ] CH canton aliases are recorded when they diverge from the canonical label set.
- [ ] CH multilingual naming issues are captured when filter or detail labels drift.
- [ ] AT authority-type or decision/commentary boundary issues are captured.
- [ ] Any stale projection or re-index issue is filed as a separate follow-up.
- [ ] Gaps are tagged as either taxonomy, filter, subtitle/detail, or operator-flow issues.

## Country 1-2 execution plan

1. Pick a small representative CH corpus and a small representative AT corpus.
2. Select 2-3 docs per country that exercise the common failure modes:
   - jurisdiction labels
   - source-family mapping
   - subtitle/context strings
   - detail metadata rows
3. Verify the search results and detail view against the shared acceptance checklist.
4. Run the operator playbook for CH and AT and capture the onboarding / triage artifacts.
5. Record any gaps as follow-up issues rather than expanding this lane to DE / FR / IT.
6. Publish a short lane summary into `TAR-160` once the slice is complete.

## Expected evidence artifacts

- Search screenshots or notes for the chosen CH and AT docs
- Detail-view screenshots or notes showing metadata rows and subtitle behavior
- Operator checklist output for CH and AT
- Run IDs or workflow URLs for any acceptance smoke or replay commands
- A compact gap list for anything that needs a follow-up issue

## Likely risks

- Canton aliases in CH drift away from canonical jurisdiction labels.
- AT authority naming blurs into commentary or decision wording.
- Stale projections hide a code-path improvement and make the slice look worse than it is.
- CH multilingual content can create false positives if the operator copy is not normalized.
- This lane can accidentally absorb DE / FR / IT work unless we keep the slice boundary explicit.

## Files and tickets touched

- New lane note: `docs/runbooks/five-country-acceptance-a.md`
- Context docs only: `docs/components/five-country-content-rollout.md`
- Context docs only: `docs/runbooks/platform-control-multi-country-operator-playbook.md`
- Context docs only: `docs/runbooks/metadata-quality-plan-status.md`
- Umbrella ticket: `TAR-160`
