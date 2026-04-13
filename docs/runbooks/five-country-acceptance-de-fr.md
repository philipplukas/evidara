# Five-Country Acceptance B: DE + FR

Owner: Platform / legal-search  
Last reviewed: 2026-04-13  
Last verified: 2026-04-13  
Applies to: countries 3-4 of the GA rollout, mapped to Germany (DE) and France (FR)

Status: Evidence execution note

## Purpose

Define the execution lane for the DE + FR rollout slice without overlapping the CH/AT baseline lane or the eventual IT consistency lane. This note is intentionally lane-specific and references the shared five-country model in `docs/components/five-country-content-rollout.md` and the shared operator playbook in `docs/runbooks/platform-control-multi-country-operator-playbook.md`.

## Current state

- `TAR-240` is the DE + FR acceptance lane for countries 3-4 of the GA rollout.
- The lane is still evidence-oriented, not a code-change lane.
- DE and FR should be validated against canonical taxonomy and shared label meaning, not by introducing new runtime overlay behavior.
- Any gaps found here should become follow-up issues or mapping fixes, not local overlay mutations.
- This note is intended to feed a compact summary into `TAR-160` once execution evidence is captured.

## Exact next checks

1. Confirm the shared source context before checking country data.
   - Re-read `docs/components/five-country-content-rollout.md`.
   - Re-read `docs/runbooks/platform-control-multi-country-operator-playbook.md`.
   - Use the current DE/FR mapping source or overlay path referenced by the active rollout notes.

2. Validate DE against the shared model.
   - Check that DE maps to canonical taxonomy dimensions without new contract keys.
   - Check that end-user filter labels keep the same meaning as the canonical labels.
   - Check that subtitles and detail context follow the shared rules.

3. Validate FR against the shared model.
   - Check that FR maps to canonical taxonomy dimensions without new contract keys.
   - Check that end-user filter labels keep the same meaning as the canonical labels.
   - Check that subtitles and detail context follow the shared rules.

4. Exercise operator flow for both countries.
   - Confirm onboarding and triage guidance stays on the shared playbook path.
   - Record any country-specific alias, translation, or naming gaps as follow-up findings.

5. Compare DE and FR for drift.
   - Confirm both countries preserve label meaning.
   - Confirm subtitle behavior stays aligned.
   - Confirm no contract drift is introduced by DE or FR overlay/copy changes.

6. If relevance evidence is needed, keep it scoped.
   - Run only a DE/FR-specific query pack.
   - Do not fold the result into the broader relevance baseline lane.

## Pass / fail capture format

Use the same compact row format for each check:

| Country | Check | Expected | Result | Evidence |
|---|---|---|---|---|
| DE | taxonomy mapping | canonical keys only, no new contract keys | PASS / FAIL | screenshot, browser note, or command output |
| DE | filters | same primary label meaning as canonical model | PASS / FAIL | screenshot, browser note, or command output |
| DE | subtitles/detail | shared subtitle and detail rules hold | PASS / FAIL | screenshot, browser note, or command output |
| DE | operator flow | onboarding and triage follow the shared playbook | PASS / FAIL | screenshot, browser note, or command output |
| FR | taxonomy mapping | canonical keys only, no new contract keys | PASS / FAIL | screenshot, browser note, or command output |
| FR | filters | same primary label meaning as canonical model | PASS / FAIL | screenshot, browser note, or command output |
| FR | subtitles/detail | shared subtitle and detail rules hold | PASS / FAIL | screenshot, browser note, or command output |
| FR | operator flow | onboarding and triage follow the shared playbook | PASS / FAIL | screenshot, browser note, or command output |

When a check fails, capture:

- the country and check name
- the exact doc IDs or examples used
- the observed mismatch
- whether it looks like mapping, translation, contract, or operator-flow drift
- the follow-up issue or owner

## Expected evidence artifacts

- DE/FR mapping checklist with pass/fail notes against canonical keys.
- Search and detail screenshots or browser captures showing shared label and subtitle behavior.
- Operator-flow evidence for onboarding and triage guidance paths.
- A short drift log covering country-specific gaps and whether each gap is a mapping issue, a translation issue, or a contract issue.
- If relevance tuning is exercised, a scoped query pack result for DE/FR examples only.

## TAR-160 summary

Paste this into `TAR-160` once the lane is executed:

> DE + FR acceptance: canonical taxonomy, filters, subtitles, and operator flow were checked against the shared five-country model. Outcome: pass for any checks that matched the shared rules; any mismatches were logged as mapping / translation / contract / operator-flow follow-ups instead of runtime overlay mutations. Evidence artifacts: DE/FR checklist, screenshots or browser notes, drift log, and optional scoped DE/FR relevance results. Owner: Platform / legal-search.

## Likely risks

- DE state-level labels may drift from canonical jurisdiction keys.
- FR legal-family naming may diverge in translated UI copy.
- Overlay content may be mutated in a way that looks like runtime state rather than reviewed configuration.
- Country-specific examples may accidentally expand into the CH/AT or IT lanes.
- Missing overlay files for DE/FR could delay evidence capture until the lane creates or references the correct mapping source.

## Files and tickets touched

- File updated: `docs/runbooks/five-country-acceptance-de-fr.md`
- Linked Linear context: `TAR-160`
- Shared source docs used for this lane:
  - `docs/components/five-country-content-rollout.md`
  - `docs/runbooks/platform-control-multi-country-operator-playbook.md`
  - `docs/runbooks/search-relevance-baseline.md`
