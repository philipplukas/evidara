# Five-Country Acceptance B: DE + FR

Owner: Platform / legal-search  
Last reviewed: 2026-04-13  
Last verified: 2026-04-13  
Applies to: countries 3-4 of the GA rollout, mapped to Germany (DE) and France (FR)

Status: Draft lane note

## Purpose

Define the acceptance lane for the DE + FR rollout slice without overlapping the CH/AT baseline lane or the eventual IT consistency lane. This note is intentionally lane-specific and references the shared five-country model in `docs/components/five-country-content-rollout.md` and the shared operator playbook in `docs/runbooks/platform-control-multi-country-operator-playbook.md`.

## Acceptance checklist

- [ ] DE maps to the canonical taxonomy dimensions without introducing new contract keys.
- [ ] FR maps to the canonical taxonomy dimensions without introducing new contract keys.
- [ ] End-user filters keep the same primary label meaning across DE and FR, even when local wording differs.
- [ ] Result subtitles and detail context follow the shared subtitle rules in both countries.
- [ ] Operator onboarding and triage guidance exists for DE and FR and stays on the shared playbook path.
- [ ] Country-specific mapping gaps are recorded as candidate fixes, not runtime overlay mutations.
- [ ] No contract drift is introduced by DE or FR overlay/copy changes.

## Country 3-4 execution plan

1. Validate the shared taxonomy against DE and FR overlay expectations.
2. Exercise legal-search filter, result, and detail semantics for representative DE and FR examples.
3. Exercise platform-control operator onboarding and triage guidance for the same two countries.
4. Capture any country-specific alias or translation gaps as follow-up findings.
5. Compare the DE and FR outputs for divergence in label meaning, subtitle behavior, and operator guidance.

## Expected evidence artifacts

- DE/FR mapping checklist with pass/fail notes against canonical keys.
- Search and detail screenshots or browser captures showing shared label and subtitle behavior.
- Operator-flow evidence for onboarding and triage guidance paths.
- A short drift log covering country-specific gaps and whether each gap is a mapping issue, a translation issue, or a contract issue.
- If relevance tuning is exercised, a scoped query pack result for DE/FR examples only.

## Likely risks

- DE state-level labels may drift from canonical jurisdiction keys.
- FR legal-family naming may diverge in translated UI copy.
- Overlay content may be mutated in a way that looks like runtime state rather than reviewed configuration.
- Country-specific examples may accidentally expand into the CH/AT or IT lanes.
- Missing overlay files for DE/FR could delay evidence capture until the lane creates or references the correct mapping source.

## Files and tickets touched

- File created: `docs/runbooks/five-country-acceptance-de-fr.md`
- Linked Linear context: `TAR-160`
- Shared source docs used for this lane:
  - `docs/components/five-country-content-rollout.md`
  - `docs/runbooks/platform-control-multi-country-operator-playbook.md`
  - `docs/runbooks/search-relevance-baseline.md`
