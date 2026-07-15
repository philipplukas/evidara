# CH BGer / BVGer Live Enablement Runbook

Owner: Platform / GA
Last reviewed: 2026-07-13
Last verified: not yet (provider ships `live_ready=false`; this runbook is the
acceptance procedure that produces the first verification)
Status: Active enablement procedure
Applies to: turning the `ch_court_decisions` provider (Bundesgericht / BGer and
Bundesverwaltungsgericht / BVGer) live on `dev`, then promoting.

## Purpose

The `ch_court_decisions` provider is fully implemented and unit-tested against a
recorded fixture ("cassette"), but **no live source has been accepted yet**. It
ships behind the loader's two-key lock:

- `ChCourtDecisionsProvider.live_ready = False`
  (`platform-control/src/platform_control/services/ch_court_decisions_provider.py`)
- blueprint templates `ch_court_decisions_bger` / `ch_court_decisions_bvger`
  ship `enabled: false`
  (`platform-control/src/platform_control/hierarchies/source_blueprints.yaml`)

Both keys must be flipped, **backed by acceptance-run evidence**, before any
court run can fire. This runbook is that acceptance procedure. Do not flip either
key from a code change alone — the flip is only justified by a captured `pass`
verdict from `scripts/ch-bger-fast-loop.sh` against a real, permitted source.

This mirrors the enablement pattern already used for the sub-federal / EU
providers (see [`five-country-acceptance-a.md`](five-country-acceptance-a.md) and
[`ch-fedlex-fast-loop-backlog.md`](ch-fedlex-fast-loop-backlog.md)); the CH court
canary is `scripts/ch-bger-fast-loop.sh`.

## What is already in place (do not re-create)

- **Provider**: `ch_court_decisions` — index discovery + per-decision fetch over
  HTML, pinned host allow-list (`bger.ch`, `bvger.ch`, `bstger.ch`, `bpger.ch`,
  `entscheidsuche.ch`), and citation extraction (docket, BGE/ATF/DTF reference,
  ECLI, DE/FR/IT decision date) hardened and covered by
  `platform-control/tests/unit/test_ch_court_decisions_provider.py`.
- **Cassette**: `platform-control/tests/fixtures/ch_court_decisions/bger_1C_123_2024.html`
  — recorded-style BGer ruling that locks parse behaviour. If a live run's shape
  differs from the cassette, update the cassette and its test in the same PR
  before flipping keys.
- **Compliance policy**: `cp_ch_court_decisions` — public-official tier,
  robots=strict, 10–20 rpm/host, 2 concurrent/host, 365-day retention,
  attribution required
  (`platform-control/src/platform_control/seeds/reference/compliance_policies.yaml`).
- **Authority binding**: `auth_bger` and `auth_bvger` both carry
  `compliance_policy_id: cp_ch_court_decisions`
  (`platform-control/src/platform_control/seeds/reference/authorities.yaml`), so
  the court policy resolves at the authority level (overriding `jur_ch_federal`'s
  Fedlex open-data policy, which is correct for legislation only).
- **Canary**: `scripts/ch-bger-fast-loop.sh` — self-hosted `--api-key` mode with
  content gates (docket, court host, decision markers, min length) and a verdict
  ladder (`pass` / `pipeline_pass_content_suspect` / `provider_failed` /
  `downstream_failed`).

## Step 0 — Choose and confirm a permitted source

Court rulings carry **no explicit open-data licence**, so the choice of source
URL matters for compliance. Two candidate families, in order of preference:

1. **Official court portals** — `www.bger.ch` weekly published rulings and
   `www.bvger.ch` decision search. These are the primary, authoritative source
   and the default host allow-list already covers them.
2. **Open aggregator** — `entscheidsuche.ch`, which republishes Swiss court
   decisions with stable per-decision URLs. Allowed by the host list; useful when
   the official portal's index is JavaScript-heavy and hard to discover from.

Before running, confirm for the chosen host:

- [ ] `robots.txt` permits the decision / index paths you will fetch. The
      `cp_ch_court_decisions` policy is `robots_mode: strict`, so a disallowed
      path **must not** be used — pick a different path or the aggregator.
- [ ] The index/listing page actually exposes per-decision links that match the
      provider's `link_pattern` (docket-in-URL or `.html`). Spot-check by opening
      the listing and confirming ruling links carry a docket like `1C_123/2024`
      (BGer) or `A-1234/2024` (BVGer).
- [ ] Request rate stays inside the policy corridor (≤ 20 rpm/host,
      ≤ 2 concurrent). The canary's `--max-resources` default of 25 is safe.
- [ ] Attribution text (`Source: Swiss Federal Courts …`) is acceptable for the
      corpus the rulings land in (`corpus_public_ch_bger_decisions` /
      `corpus_public_ch_bvger_decisions`).

Record the exact `index_urls` (preferred) or `seed_urls` you confirmed — they go
into the template `seed_urls` at flip time (Step 3), replacing the placeholder
landing pages currently committed.

## Step 1 — Run the acceptance canary to a `pass` verdict

The canary must be pointed at an environment whose template has been enabled.
Because that is the very thing this runbook gates, run the canary in the enabling
environment against a **temporary, manually-enabled** template revision (dev
first). Sequence:

1. Deploy the current `platform-control` to `dev` (or self-hosted) so the
   hardened provider + cassette are live in the image.
2. Temporarily enable the BGer template in the running environment (see Step 3
   for the file locations; on dev you may apply the flip, validate, and only
   commit it once the canary passes). Point its `seed_urls` / `index_urls` at the
   source confirmed in Step 0.
3. Run the canary in self-hosted mode:

   ```bash
   scripts/ch-bger-fast-loop.sh \
     --api-key "$EVIDARA_PLATFORM_CONTROL_API_KEY" \
     --pc-url "$EVIDARA_PLATFORM_CONTROL_URL" \
     --ls-url "$EVIDARA_LEGAL_SEARCH_URL" \
     --template ch_court_decisions_bger \
     --max-resources 25 \
     --copy-evidence
   ```

   For BVGer, rerun with `--template ch_court_decisions_bvger` (the script maps
   this to `auth_bvger` automatically).

4. Require **`verdict: pass`**. The ladder tells you where to look if not:
   - `provider_failed` — acquisition/host/discovery problem (check Step 0 source
     choice, `robots.txt`, and `link_pattern`).
   - `downstream_failed` — DI handoff / lifecycle (worker artifact-store + Pub/Sub
     parity, as in the AT RIS case — see
     [`evidence/2026-04-14-at-ris-fast-loop-run1.md`](evidence/2026-04-14-at-ris-fast-loop-run1.md)).
   - `pipeline_pass_content_suspect` — pipeline ran but content gates (docket /
     court host / decision markers / min length) were weak. Inspect the captured
     HTML; if the parser genuinely mis-read it, fix the provider + cassette and
     restart from Step 1.

   Note: the canary's decision-marker gate matches German markers
   (`Erwägung|Bundesgericht|Urteil`). A French/Italian-only BVGer slice may trip
   `pipeline_pass_content_suspect` on that gate even when parsing is correct —
   confirm the docket/court/ECLI/date extraction on the captured resource before
   judging, and prefer a German ruling for the first BGer acceptance run.

## Step 2 — Capture evidence

The canary with `--copy-evidence` writes
`docs/runbooks/evidence/ch-bger-fast-loop-<UTC-date>.md` (via
`copy_evidence_to_repo` in `scripts/fast-loop-evidence.sh`). Commit that file.

The evidence note must show, at minimum:

- `run_id`, `source_id`, `source_version_id`
- `status=completed` and `verdict=pass`
- `content_type_html_count ≥ 1`, `captured_count ≥ 1`, `raw_artifact_count ≥ 1`
- downstream `accepted / processing / canonical_ready` all ≥ 1
- lifecycle `document.processed` ≥ 1
- content gates `title_ok`, `court_host_ok`, `docket_ok`, `decision_marker_ok`,
  `min_content_length_ok` all satisfied

Mirror the layout of
[`evidence/2026-04-14-at-ris-fast-loop-run1.md`](evidence/2026-04-14-at-ris-fast-loop-run1.md):
one note per court (BGer and BVGer), each with canonical inputs
(`jurisdiction_id=jur_ch_federal`, `authority_id=auth_bger`/`auth_bvger`,
`overlay_id=ch`), the source/version/run IDs, and the checks block.

## Step 3 — Flip the two keys (only after `pass` evidence exists)

With committed `pass` evidence for each court you are enabling:

1. **Provider key** — in
   `platform-control/src/platform_control/services/ch_court_decisions_provider.py`:

   ```python
   class ChCourtDecisionsProvider:
       provider_name = "ch_court_decisions"
       live_ready = True   # was False
   ```

   Also update `test_provider_is_scaffold_until_live_enablement` (which asserts
   `live_ready is False`) in the same PR, or remove it — otherwise the unit suite
   fails by design, which is the intended tripwire.

2. **Template keys** — in
   `platform-control/src/platform_control/hierarchies/source_blueprints.yaml`,
   set `enabled: true` on the template(s) you produced evidence for, and replace
   the placeholder `seed_urls` (`https://www.bger.ch/` /
   `https://www.bvger.ch/`) with the confirmed `index_urls` / `seed_urls` from
   Step 0:

   ```yaml
   ch_court_decisions_bger:
     provider: ch_court_decisions
     index_urls:
       - https://www.bger.ch/…   # confirmed weekly-rulings listing
     court: bger
     …
     enabled: true               # was false
   ```

   Enable BVGer only if you captured BVGer `pass` evidence; the two courts are
   independent and may be enabled in separate PRs.

3. **Do not touch** `cp_ch_court_decisions`, `auth_bger`, or `auth_bvger` — the
   compliance policy and authority-level binding are already correct.

## Step 4 — Confirm searchability

After the flip is deployed:

- [ ] Re-run `scripts/ch-bger-fast-loop.sh` against the committed template (no
      manual enable needed now) and confirm `pass` — this proves the two-key lock
      no longer blocks the run.
- [ ] Confirm the canonical documents are searchable in legal-search: query the
      captured docket (e.g. `1C_123/2024`) and a court term (`Bundesgericht`)
      and verify the ruling appears with the right authority attribution. Capture
      a short relevance note under `docs/runbooks/evidence/` mirroring
      [`evidence/2026-04-14-dev-relevance-pack.md`](evidence/2026-04-14-dev-relevance-pack.md).
- [ ] Only after dev is green, promote the same flip to staging/prod following
      [`compliance-policy-staging-rollout.md`](compliance-policy-staging-rollout.md).

## Rollback

If a live court run misbehaves after enablement:

1. Set the affected template back to `enabled: false` (fastest, per-court) and
   redeploy — this re-arms the two-key lock without touching the provider.
2. If the provider itself regresses, set `live_ready = False` to disable all
   court templates at once.
3. Re-run the canary to confirm runs are blocked again, and capture a short
   incident note under `docs/runbooks/evidence/`.

## Checklist summary

- [ ] Step 0 — permitted source confirmed (robots, rate, link pattern, attribution)
- [ ] Step 1 — canary `pass` for BGer (and BVGer if enabling)
- [ ] Step 2 — evidence committed under `docs/runbooks/evidence/`
- [ ] Step 3 — `live_ready=True` + template `enabled: true` + real seed/index URLs
- [ ] Step 4 — post-flip canary `pass` + searchability confirmed
- [ ] Promotion to staging/prod scheduled
