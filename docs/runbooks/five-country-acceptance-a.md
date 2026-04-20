# Five-Country Acceptance A (CH + AT)

Owner: Platform / GA
Last reviewed: 2026-04-14
Last verified: 2026-04-14
Status: Active evidence execution note
Applies to: country slice 1-2 only

## Purpose

Define the execution lane for the first country slice of the five-country GA umbrella.
This lane covers Switzerland (CH) and Austria (AT) only and stays out of the DE / FR / IT
content-lane work so we can validate the shared model without overlap.

Canonical source context:

- [Five-Country Content Rollout](../components/five-country-content-rollout.md)
- [Platform-Control Multi-Country Operator Playbook](platform-control-multi-country-operator-playbook.md)
- [CH + AT Thin-Slice Execution](ch-at-thin-slice-execution.md)
- [CH Fedlex Fast-Loop Backlog](ch-fedlex-fast-loop-backlog.md)
- [Metadata quality plan status](metadata-quality-plan-status.md)
- Linear umbrella: `TAR-160`

## Current state

- The lane is no longer just theoretical: CH/AT overlay and seed consistency checks now pass in-repo.
- The shared country model is already in place; this lane now has repo-backed fixture evidence, but still needs live browser/operator evidence if we want a full operator proof packet.
- The umbrella target is `TAR-160`; this note should produce a compact summary that can be pasted there verbatim.
- Do not expand scope into DE / FR / IT or into branch-policy / runner work.

## 2026-04-13 execution snapshot

- `python3 scripts/check_country_overlay.py --country CH` -> pass.
- `python3 scripts/check_country_overlay.py --country AT` -> pass.
- `python3 scripts/check_country_overlay_at.py` -> pass.
- Live CH deterministic preview run executed on dev:
  - evidence: [2026-04-13 CH Fedlex Thin Slice Run 1](evidence/2026-04-13-ch-fedlex-thin-slice-run1.md)
  - result: technical pass with `config-change-needed`
  - key finding: provider captured the Fedlex homepage shell only, not a legislation page
  - key mapping note: live dev required `jur_ch_federal` + `auth_fedlex`, not `jur_ch` + `auth_ch_fedlex`
  - follow-up finding: Fedlex metadata is publicly queryable via `https://fedlex.data.admin.ch/sparqlendpoint`, which strengthens the case for a deterministic CH discovery layer, but not via the current `deterministic_http` homepage blueprint
- Live CH SPARQL preview run executed on dev:
  - evidence: [2026-04-13 CH Fedlex SPARQL Preview Run 1](evidence/2026-04-13-ch-fedlex-sparql-preview-run1.md)
  - result: technical pass with `config-change-needed`
  - key finding: acquisition, DI ingress, and DI callback paths all worked
  - key caveat: the provider currently emits metadata-plus-Turtle JSON, not a text-bearing Swiss law artifact
  - operator note: the first manual lifecycle poll was too early; downstream rows appeared after the Pub/Sub round-trip completed
- `platform-control/tests/fixtures/scraping_baseline/ch_commentary_html.json` anchors CH commentary evidence with `jurisdiction_id: jur_ch_federal`, `authority_id: auth_commentary_publisher`, `document_type_hint: commentary`, `language_codes: de`.
- `platform-control/tests/fixtures/scraping_baseline/clean_html.json`, `xml_primary.json`, and `multi_language_fr_de.json` provide additional CH law fixtures, including multilingual `fr,de,it` coverage for the structured-law slice.
- `platform-control/tests/fixtures/scraping_baseline/at_ris_decision.json` anchors AT decision evidence with `jurisdiction_id: jur_at_federal`, `authority_id: auth_vfgh`, `document_type_hint: decision`, `language_codes: de`.
- `platform-control/seeds/reference/{jurisdictions,authorities}.yaml` contains the canonical CH/AT seed rows (`jur_ch`, `jur_ch_federal`, `jur_at`, `jur_at_federal`, and their authorities).
- `contracts/vocabularies/jurisdiction.json` and the search/projection contracts already constrain the canonical jurisdiction and projection fields used by these fixtures.
- Not executed here: live browser screenshots, operator workflow URLs, and `uv run pytest platform-control/tests/unit/test_scraping_fixture_baseline.py -q` in this shell (the current Python environment cannot spawn `pytest`).

## 2026-04-14 AT fast-loop status

- Branch `codex/at-ris-fast-loop` carries:
  - the AT narrow/small-batch templates
  - the AT fast-loop script
  - the RIS async-dispatch + fail-fast timeout patch
- Live `dev` now proves two clean AT fast-loop passes:
  - narrow:
    - template `ris_ogd_bundesrecht_narrow_html`
    - run `run_01kp5xqgrfyqq2abez3r666d9h`
  - tiny widened batch:
    - template `ris_ogd_bundesrecht_small_batch_html`
    - run `run_01kp5xrqvh61xfdace1x9sqed1`
- Evidence:
  - [2026-04-14 AT RIS Fast Loop Run 1](evidence/2026-04-14-at-ris-fast-loop-run1.md)
- Root cause recovered during execution:
  - the first AT rerun failed downstream because `platform-control-worker-dev` was missing the
    GCS artifact-store and Pub/Sub env vars that `platform-control-api-dev` already had
  - once worker env parity was restored, DI and lifecycle rows appeared as expected
- Operational note:
  - live dev uses `authority_id=auth_ris`
  - the AT fast loop now auto-detects the live RIS authority instead of assuming the older
    `auth_at_ris` seed name

## Pass / fail snapshot

| Check | Sample | Result | Evidence |
|------|--------|--------|----------|
| CH overlay consistency | `country-overlays/at/*` + CH source blueprints | pass | `python3 scripts/check_country_overlay.py --country CH` |
| AT overlay consistency | `country-overlays/at/*` + AT source blueprints | pass | `python3 scripts/check_country_overlay.py --country AT` |
| AT contract + seed consistency | `contracts/vocabularies/jurisdiction.json` + `platform-control/seeds/reference/{jurisdictions,authorities}.yaml` | pass | `python3 scripts/check_country_overlay_at.py` |
| CH fixture anchors | `ch_commentary_html.json`, `clean_html.json`, `xml_primary.json`, `multi_language_fr_de.json` | pass | repo-backed fixture files with canonical CH jurisdiction / authority fields |
| CH live deterministic thin slice | `run_01kp3rqx5nw6gyyrtnzcy48z3y` | partial pass / config-change-needed | [2026-04-13 CH Fedlex Thin Slice Run 1](evidence/2026-04-13-ch-fedlex-thin-slice-run1.md) |
| AT fixture anchors | `at_ris_decision.json` | pass | repo-backed fixture file with canonical AT jurisdiction / authority fields |
| AT live narrow fast loop | `run_01kp5xqgrfyqq2abez3r666d9h` | pass | [2026-04-14 AT RIS Fast Loop Run 1](evidence/2026-04-14-at-ris-fast-loop-run1.md) |
| AT live tiny batch fast loop | `run_01kp5xrqvh61xfdace1x9sqed1` | pass | [2026-04-14 AT RIS Fast Loop Run 1](evidence/2026-04-14-at-ris-fast-loop-run1.md) |
| Live browser/operator evidence | CH/AT screenshots, workflow URLs, run IDs | partial pass | run IDs are captured for CH and AT; browser screenshots are still outside this lane |
| Fixture baseline pytest | `platform-control/tests/unit/test_scraping_fixture_baseline.py` | not run | current shell cannot spawn `pytest` |

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
6. Publish the `TAR-160` summary block below once the slice is complete.

## Exact next checks

- Confirm the CH corpus returns the expected canonical jurisdiction, source-family, and authority labels.
- Confirm the AT corpus returns the same canonical labels without country-specific alias drift.
- Confirm result subtitles and detail rows match the shared subtitle rules and do not fall back to `unknown`.
- Confirm the operator flow can select the country overlay, onboard the source, and complete triage end to end.
- Confirm any mismatch is recorded as a follow-up issue instead of being patched in this lane.

## Pass / fail capture format

Use one row per checked document or operator step:

| Check | Sample | Result | Evidence |
|------|--------|--------|----------|
| CH taxonomy / filters | `<doc-id or query>` | pass / fail | `<run URL, screenshot, or log anchor>` |
| AT taxonomy / filters | `<doc-id or query>` | pass / fail | `<run URL, screenshot, or log anchor>` |
| Subtitle / detail rows | `<doc-id or query>` | pass / fail | `<screenshot or note>` |
| Operator flow | `<step name>` | pass / fail | `<workflow URL or log anchor>` |

Capture rule:

- If a check fails, add the exact symptom, the smallest reproducible sample, and a follow-up issue reference.
- If a check passes, keep the evidence pointer short and copyable so it can be pasted into `TAR-160`.

## Expected evidence artifacts

- Search screenshots or notes for the chosen CH and AT docs
- Detail-view screenshots or notes showing metadata rows and subtitle behavior
- Operator checklist output for CH and AT
- Run IDs or workflow URLs for any acceptance smoke or replay commands
- A compact gap list for anything that needs a follow-up issue

## TAR-160 summary block

Paste this into `TAR-160` when the slice is complete:

> CH + AT acceptance is materially advanced.
> Representative CH and AT docs were checked for overlay/model consistency and repo-backed fixture anchors.
> Result: CH live fast-loop evidence exists, and AT now has clean live narrow and tiny-batch RIS fast-loop passes on dev.
> Evidence: `python3 scripts/check_country_overlay.py --country CH`, `python3 scripts/check_country_overlay.py --country AT`, `python3 scripts/check_country_overlay_at.py`, [2026-04-13 CH Fedlex SPARQL Preview Run 1](evidence/2026-04-13-ch-fedlex-sparql-preview-run1.md), [2026-04-14 AT RIS Fast Loop Run 1](evidence/2026-04-14-at-ris-fast-loop-run1.md), `platform-control/tests/fixtures/scraping_baseline/ch_commentary_html.json`, `platform-control/tests/fixtures/scraping_baseline/at_ris_decision.json`, `platform-control/tests/fixtures/scraping_baseline/clean_html.json`, `platform-control/tests/fixtures/scraping_baseline/xml_primary.json`, `platform-control/tests/fixtures/scraping_baseline/multi_language_fr_de.json`.
> Gaps: browser screenshots and any additional operator UI captures remain optional follow-on evidence, not current blockers for the fast-loop lane.
> Next action: sync the CH/AT run IDs and operator judgment into `TAR-160`, then decide whether to widen AT or move to the next country lane.

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
