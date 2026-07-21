# CH + AT Thin-Slice Execution

Owner: Platform / GA
Last reviewed: 2026-04-14
Last verified: 2026-04-14
Applies to: CH and AT first-country execution toward GA

## Purpose

This runbook turns the CH/AT country lane into an execution sequence operators can run end to
end. It covers:

1. jurisdiction and authority setup
2. authority discovery
3. source and source-version creation
4. preview / production runs
5. retries and recovery
6. when to use an AI-assisted thin-slice approach versus a deterministic high-precision path

Use this as the operational companion to:

- [Five-Country Acceptance A (CH + AT)](five-country-acceptance-a.md)
- [Platform-Control Multi-Country Operator Playbook](platform-control-multi-country-operator-playbook.md)
- [Firecrawl Preview Run](firecrawl-preview-run.md)
- [First Vertical Slice Exit Gates](first-vertical-slice-exit-gates.md)
- [CH Fedlex SPARQL Provider and Temporal Orchestration](../architecture/ch-fedlex-sparql-temporal-architecture.md)
- [CH Fedlex Fast-Loop Backlog](ch-fedlex-fast-loop-backlog.md)

## Recommended posture

Start CH and AT with the narrowest credible slices, then widen only after preview evidence is
clean.

### CH recommended sequence

1. `CH slice 1` — deterministic federal legislation
   - overlay: `ch`
   - template: `deterministic_http_fedlex_legislation`
   - live canonical pair: `jur_ch_federal` + `auth_fedlex`
   - goal: prove canonical jurisdiction/language/subtitle/detail handling on a trusted source

2. `CH slice 2` — exploratory canton / court discovery
   - use only after slice 1 is stable
   - current repo does not yet ship a dedicated CH crawl blueprint, so this is a follow-on setup
   - goal: discover canton/court path structure before freezing a deterministic or tightly
     constrained crawl spec

### AT recommended sequence

1. `AT slice 1` — deterministic federal legal content
   - overlay: `at`
   - template: `ris_ogd_bundesrecht`
   - authority: live dev currently resolves to `auth_ris`
   - goal: prove high-trust acquisition and readiness on the RIS-backed path

2. `AT slice 2` — exploratory justice-portal crawl
   - overlay: `at`
   - template: `firecrawl_justice_portal`
   - authority: usually still `auth_ris` for the first discovery pass
   - goal: discover decision/commentary boundaries, path patterns, and authority labels before
     locking a more precise source version

## AT RIS reality check from live dev

The live AT fast-loop runs on `2026-04-14` clarified the right steady-state shape for RIS-backed
acquisition:

- `POST /v1/runs` must return quickly with a `pending` run
- the worker should own the actual RIS fetch
- the worker must share the same artifact-store and event-publisher settings as the API

Confirmed live signals:

- narrow pass:
  - `run_01kp5xqgrfyqq2abez3r666d9h`
- tiny batch pass:
  - `run_01kp5xrqvh61xfdace1x9sqed1`
- evidence:
  - [2026-04-14 AT RIS Fast Loop Run 1](evidence/2026-04-14-at-ris-fast-loop-run1.md)

Operational implication:

- keep AT RIS on the async worker-backed path
- keep fail-fast provider timeouts so slow RIS fetches produce failed runs, not hanging HTTP calls
- require worker env parity for:
  - `PLATFORM_CONTROL_ARTIFACT_STORE_BACKEND`
  - `PLATFORM_CONTROL_EVENT_PUBLISHER_BACKEND`
  - raw artifact bucket and Pub/Sub topics
- without that parity, the worker writes `file:///app/...` bundle manifests that DI cannot read
  cross-service

## AI-first vs deterministic

Use the following rule:

| Situation | Recommended approach | Why |
|---|---|---|
| Known official corpus with stable structure | deterministic first | best precision, repeatability, and replay safety |
| Known API/OGD source with good identifiers | deterministic / API first | avoids hallucinated structure and over-crawl |
| Unknown or mixed portal structure | AI-assisted discovery first | faster path to candidate URLs, authority labels, and page classes |
| Broad crawl intended for production | do not ship AI-only | convert preview findings into reviewed deterministic or tightly bounded acquisition config |

### Practical recommendation for CH/AT

- `CH` federal legislation should start deterministic, not AI-first.
- `AT` RIS should start deterministic, not AI-first.
- AI-assisted discovery is appropriate for:
  - AT justice-portal exploration
  - later CH canton / court exploration
  - identifying include/exclude paths, candidate authority names, and page families

### What “AI-assisted” should mean here

Use AI for:

- broad preview runs on a constrained source
- summarizing captured resources into candidate authority/page-type buckets
- proposing include/exclude path rules
- proposing source-family labels for operator review

Do **not** use AI as the final source of truth for:

- canonical jurisdiction keys
- authority IDs
- source-family contract values
- production acceptance without operator review

The production path should always end with a reviewed acquisition spec, approved source version,
and run-scoped evidence.

## CH Fedlex reality check from live dev

The first live CH Fedlex deterministic preview exposed a more precise system boundary:

- the public `www.fedlex.admin.ch` and `fedlex.data.admin.ch` document URLs are SPA-style surfaces
  when fetched via raw HTTP
- the Fedlex metadata app renders real legal metadata in the browser
- that metadata app is backed by a public SPARQL endpoint and a browser `POST` query flow

Confirmed live signals:

- public SPARQL endpoint: `https://fedlex.data.admin.ch/sparqlendpoint`
- work resource example: `https://fedlex.data.admin.ch/eli/cc/1999/404`
- expression resources resolved deterministically via SPARQL:
  - `.../de`
  - `.../fr`
  - `.../it`
  - `.../en`
  - `.../rm`

Operational implication:

- keep the CH posture deterministic-first at the evidence/authority level
- do not assume `deterministic_http` against raw Fedlex page URLs is sufficient for legislation
  text capture
- the new `fedlex_sparql` path proves the technical handoff through DI, but it currently emits a
  metadata-plus-Turtle JSON bundle rather than a text-bearing law artifact
- if we stay purely deterministic, the stronger long-term option is a CH API/SPARQL-aware
  acquisition path
- use Temporal above that provider for hierarchy traversal, retries, and backfills rather than
  as a replacement for provider logic
- until that exists, use one tiny AI-assisted or JS-capable discovery slice only to identify stable
  legislation entry patterns, then convert back into reviewed deterministic config where possible

## Step 1: Confirm or create reference data

### Existing repo-backed CH/AT reference anchors

- `platform-control/src/platform_control/seeds/reference/jurisdictions.yaml`
  - `jur_ch`
  - `jur_at`
- `platform-control/src/platform_control/seeds/reference/authorities.yaml`
  - `auth_ch_fedlex`
  - `auth_zh_admin`
- `auth_at_ris`
- `auth_ris`
  - `auth_at_ogh`
  - `auth_at_vfgh`
  - `auth_at_vwgh`

### Important live-environment note

The repo still carries older CH seed names such as `auth_ch_fedlex`, but the live dev hierarchy
and runtime tests are aligned on the stricter federal pair:

- `jur_ch_federal`
- `auth_fedlex`

Use the live canonical pair when executing the first deterministic CH Fedlex slice against dev.
Treat the seed/runtime mismatch as evidence to capture, not as something to silently normalize away.

AT has the same practical wrinkle on dev:

- repo seed naming may still reference `auth_at_ris`
- live dev currently resolves the RIS authority as `auth_ris`

The AT fast loop should prefer `auth_ris` and auto-detect the live RIS authority by slug/name if
the exact ID drifts again.

### API paths

- `GET /v1/reference-data/jurisdictions`
- `POST /v1/reference-data/jurisdictions`
- `GET /v1/reference-data/authorities`
- `POST /v1/reference-data/authorities`

### Example create requests

Use only if the target environment is missing the rows.

```bash
curl -X POST "$EVIDARA_PLATFORM_CONTROL_URL/v1/reference-data/jurisdictions" \
  -H "Authorization: Bearer $EVIDARA_PLATFORM_CONTROL_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"Switzerland","slug":"ch"}'
```

```bash
curl -X POST "$EVIDARA_PLATFORM_CONTROL_URL/v1/reference-data/jurisdictions" \
  -H "Authorization: Bearer $EVIDARA_PLATFORM_CONTROL_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"Austria","slug":"at"}'
```

```bash
curl -X POST "$EVIDARA_PLATFORM_CONTROL_URL/v1/reference-data/authorities" \
  -H "Authorization: Bearer $EVIDARA_PLATFORM_CONTROL_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"jurisdiction_id":"jur_ch","name":"Fedlex","slug":"ch-fedlex"}'
```

```bash
curl -X POST "$EVIDARA_PLATFORM_CONTROL_URL/v1/reference-data/authorities" \
  -H "Authorization: Bearer $EVIDARA_PLATFORM_CONTROL_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"jurisdiction_id":"jur_at","name":"Rechtsinformationssystem des Bundes","slug":"at-ris"}'
```

## Step 2: Authority discovery

### Deterministic-first path

If the authority is already known and seeded:

1. use the seeded authority directly
2. skip exploratory crawling
3. go straight to blueprint preview and source creation

This is the correct path for:

- `CH / auth_fedlex`
- `AT / auth_at_ris`

### AI-assisted discovery path

Use this when the portal is large and the authority/page structure is not yet fully normalized.

Recommended process:

1. preview the blueprint that best matches the source
2. create a draft source version only for preview
3. run a small preview slice with a bounded scope
4. review:
   - preview summary
   - captured resources
   - authority labels
   - content-type mix
   - obvious source-family boundaries
5. convert the findings into:
   - reviewed authority rows
   - tighter include/exclude rules
   - a production candidate source version

Use this for:

- `AT / firecrawl_justice_portal`
- future CH canton/court exploration once a CH crawl blueprint exists

## Step 3: Preview the acquisition blueprint

Always preview the overlay/template first.

### CH SPARQL preview

```bash
curl -X POST "$EVIDARA_PLATFORM_CONTROL_URL/v1/sources/blueprint-preview" \
  -H "Authorization: Bearer $EVIDARA_PLATFORM_CONTROL_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"overlay_id":"ch","provider_template_id":"fedlex_sparql_constitution_de"}'
```

### CH deterministic preview

```bash
curl -X POST "$EVIDARA_PLATFORM_CONTROL_URL/v1/sources/blueprint-preview" \
  -H "Authorization: Bearer $EVIDARA_PLATFORM_CONTROL_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"overlay_id":"ch","provider_template_id":"deterministic_http_fedlex_legislation"}'
```

### AT deterministic preview

```bash
curl -X POST "$EVIDARA_PLATFORM_CONTROL_URL/v1/sources/blueprint-preview" \
  -H "Authorization: Bearer $EVIDARA_PLATFORM_CONTROL_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"overlay_id":"at","provider_template_id":"ris_ogd_bundesrecht"}'
```

### AT exploratory preview

```bash
curl -X POST "$EVIDARA_PLATFORM_CONTROL_URL/v1/sources/blueprint-preview" \
  -H "Authorization: Bearer $EVIDARA_PLATFORM_CONTROL_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"overlay_id":"at","provider_template_id":"firecrawl_justice_portal"}'
```

Expected result:

- `200`
- expanded acquisition spec
- provider is one of:
  - `deterministic_http`
  - `ris_ogd`
  - `firecrawl`
  - `fedlex_sparql`

### Reusing a template with your own seeds

Most new sources are "a portal we already reach, different documents". You do not need a
new template for that, and you must not hand-write a full `acquisition_spec` for it —
that discards blueprint provenance, and with it the ADR-0030 config key that gates the
run. Send `blueprint_overrides` alongside the template instead (#710, ADR-0045):

```bash
curl -X POST "$EVIDARA_PLATFORM_CONTROL_URL/v1/sources/blueprint-preview" \
  -H "Authorization: Bearer $EVIDARA_PLATFORM_CONTROL_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "overlay_id": "ch",
    "provider_template_id": "fedlex_sparql_federal_law_batch_de",
    "blueprint_overrides": {
      "seed_urls": [
        "https://fedlex.data.admin.ch/eli/cc/2008/414",
        "https://fedlex.data.admin.ch/eli/cc/2008/416"
      ]
    }
  }'
```

The same `blueprint_overrides` object is accepted by `POST /v1/sources/with-version` and
`POST /v1/sources/{source_id}/versions`. Everything except the seeds — provider, tenant,
corpus, scope, trust tier, SPARQL endpoint, extractor profile — stays the template's.

Two refusals are expected and correct:

- `409` for a seed on a host the template's own seeds do not reach — a template's
  enablement is acceptance-run evidence about **one** portal, not a licence to crawl;
- `409` for any override on a template that declares no seeds of its own (`ris_ogd`,
  `legifrance`) — those providers are not seed-driven and have no vetted origin to
  inherit.

Needing a *non-seed* field to differ still means you need a template, which is a repo
change and a deploy. That is deliberate: `source_blueprints.yaml` is the list of portals
the platform may reach, and adding one is a reviewed decision.

## Step 4: Create source + initial version

Prefer `POST /v1/sources/with-version` for the thin-slice path — but only the **first**
time. Re-running these snippets mints a second source for the same law, and because the
pipeline keys document identity off the source, a second document too. To re-acquire, add
a version to the source you already have: `POST /v1/sources/{source_id}/versions`. The
`*-fast-loop.sh` harnesses do this automatically (#766).

### CH slice 1: Fedlex legislation

```bash
curl -X POST "$EVIDARA_PLATFORM_CONTROL_URL/v1/sources/with-version" \
  -H "Authorization: Bearer $EVIDARA_PLATFORM_CONTROL_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "source": {
      "name": "CH Fedlex legislation thin slice",
      "jurisdiction_id": "jur_ch_federal",
      "authority_id": "auth_fedlex",
      "source_type": "website",
      "document_family": "law"
    },
    "source_version": {
      "version_label": "ch-fedlex-v1",
      "overlay_id": "ch",
      "provider_template_id": "deterministic_http_fedlex_legislation"
    }
  }'
```

Latest evidence:

- [2026-04-13 CH Fedlex Thin Slice Run 1](evidence/2026-04-13-ch-fedlex-thin-slice-run1.md)
- current judgment: `config-change-needed`
- key blocker: homepage shell capture rather than legislation-page capture

### CH slice 1b: Fedlex SPARQL constitution

```bash
curl -X POST "$EVIDARA_PLATFORM_CONTROL_URL/v1/sources/with-version" \
  -H "Authorization: Bearer $EVIDARA_PLATFORM_CONTROL_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "source": {
      "name": "CH Fedlex SPARQL constitution thin slice",
      "jurisdiction_id": "jur_ch_federal",
      "authority_id": "auth_fedlex",
      "source_type": "api",
      "document_family": "law"
    },
    "source_version": {
      "version_label": "ch-fedlex-sparql-v1",
      "overlay_id": "ch",
      "provider_template_id": "fedlex_sparql_constitution_de"
    }
  }'
```

Latest evidence:

- [2026-04-13 CH Fedlex SPARQL Preview Run 1](evidence/2026-04-13-ch-fedlex-sparql-preview-run1.md)
- current judgment: `config-change-needed`
- key blocker: metadata/Turtle JSON captured successfully, but the provider does not yet emit a
  text-bearing law artifact

### AT slice 1: RIS Bundesrecht

```bash
curl -X POST "$EVIDARA_PLATFORM_CONTROL_URL/v1/sources/with-version" \
  -H "Authorization: Bearer $EVIDARA_PLATFORM_CONTROL_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "source": {
      "name": "AT RIS Bundesrecht thin slice",
      "jurisdiction_id": "jur_at",
      "authority_id": "auth_ris",
      "source_type": "api",
      "document_family": "law"
    },
    "source_version": {
      "version_label": "at-ris-bundesrecht-v1",
      "overlay_id": "at",
      "provider_template_id": "ris_ogd_bundesrecht"
    }
  }'
```

### AT slice 2: exploratory justice portal

```bash
curl -X POST "$EVIDARA_PLATFORM_CONTROL_URL/v1/sources/with-version" \
  -H "Authorization: Bearer $EVIDARA_PLATFORM_CONTROL_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "source": {
      "name": "AT justice portal discovery slice",
      "jurisdiction_id": "jur_at",
      "authority_id": "auth_ris",
      "source_type": "website",
      "document_family": "decision"
    },
    "source_version": {
      "version_label": "at-justice-discovery-v1",
      "overlay_id": "at",
      "provider_template_id": "firecrawl_justice_portal"
    }
  }'
```

## Step 5: Approve the source version

Production runs should use approved versions only. Preview runs can still use draft versions in
some flows, but the safe operator path is to approve once the acquisition spec is validated.

```bash
curl -X POST "$EVIDARA_PLATFORM_CONTROL_URL/v1/versions/$SOURCE_VERSION_ID/approve" \
  -H "Authorization: Bearer $EVIDARA_PLATFORM_CONTROL_TOKEN"
```

Approval checklist for CH/AT:

- `jurisdiction` aligns to canonical CH/AT keys
- `source_family` matches `law`, `decision`, `commentary`, or `administrative_guidance`
- language defaults are correct
- CH canton/federal distinction or AT authority taxonomy is explicit

## Step 6: Trigger preview runs as thin slices

Use `mode=preview` first.

### Full-source preview

```bash
curl -X POST "$EVIDARA_PLATFORM_CONTROL_URL/v1/runs" \
  -H "Authorization: Bearer $EVIDARA_PLATFORM_CONTROL_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"source_id\": \"$SOURCE_ID\",
    \"source_version_id\": \"$SOURCE_VERSION_ID\",
    \"mode\": \"preview\"
  }"
```

### Bounded discovery preview

Use this for AI-assisted or exploratory passes.

```bash
curl -X POST "$EVIDARA_PLATFORM_CONTROL_URL/v1/runs" \
  -H "Authorization: Bearer $EVIDARA_PLATFORM_CONTROL_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"source_id\": \"$SOURCE_ID\",
    \"source_version_id\": \"$SOURCE_VERSION_ID\",
    \"mode\": \"preview\",
    \"scope\": {
      \"kind\": \"discovered_subset\",
      \"max_resources\": 25
    }
  }"
```

Use bounded preview when:

- you are exploring a broad portal
- you want path/classification signal before full coverage
- you are testing retries without re-running a large job

Operator note:

- for the current CH SPARQL path, treat downstream `processing-status` and `document-lifecycle`
  as eventually consistent
- wait roughly `20-30s` after run completion before concluding DI is missing
- if DI rows appear but the artifact is still JSON metadata only, that is a provider-output issue,
  not a transport issue

## Step 7: Inspect and classify the run

After the run starts, inspect:

- `GET /v1/runs/{run_id}`
- `GET /v1/runs/{run_id}/provider-jobs`
- `GET /v1/runs/{run_id}/preview-summary`
- `GET /v1/runs/{run_id}/captured-resources`
- `GET /v1/runs/{run_id}/raw-artifacts`
- `GET /v1/runs/{run_id}/processing-status`
- `GET /v1/runs/{run_id}/document-lifecycle`

### What “good” looks like

For CH/AT thin slices:

- run reaches `completed`
- provider job exists and is not stuck
- captured resources are non-zero
- preview summary shows plausible content-type mix
- language coverage matches expectations
- authority/jurisdiction labels remain canonical
- downstream processing emits run-scoped status and document-lifecycle rows

## Step 8: Retries and recovery

Retry only terminal runs:

- `failed`
- `cancelled`

Do not retry:

- `pending`
- `running`

API:

```bash
curl -X POST "$EVIDARA_PLATFORM_CONTROL_URL/v1/runs/$RUN_ID/retry" \
  -H "Authorization: Bearer $EVIDARA_PLATFORM_CONTROL_TOKEN"
```

Repo-backed retry behavior:

- inline backend: retry redispatches and puts the run back into `running`
- worker backend: retry resets to `pending` and clears stale provider jobs

Relevant coverage:

- `platform-control/tests/unit/test_run_service.py::test_retry_run_redispatches_when_inline_backend`
- `platform-control/tests/unit/test_run_service.py::test_retry_run_worker_backend_leaves_pending_and_clears_provider_jobs`
- `platform-control/tests/unit/test_run_service.py::test_retry_run_rejects_non_terminal_states`

Retry before editing config when:

- failure is provider timeout or transient connectivity
- callback delivery was delayed
- artifact store path was temporarily unavailable

Edit config before retrying when:

- preview summary shows wrong page family mix
- include/exclude rules are clearly too broad or too narrow
- authority discovery signal is noisy

## Step 9: Promote from thin slice to production candidate

Promote only after:

1. preview summary is plausible
2. captured resources are non-zero and on-target
3. authority/jurisdiction mapping stays canonical
4. a retry path was proven or judged unnecessary
5. downstream processing and search evidence are attached

For CH/AT specifically:

- CH should prove federal legislation first before canton/court expansion
- AT should prove RIS first before broader justice-portal exploration becomes production-facing

## Recommended execution order for right now

1. `CH deterministic`: `auth_ch_fedlex` + `deterministic_http_fedlex_legislation`
2. `AT deterministic`: `auth_ris` + `ris_ogd_bundesrecht`
3. `AT AI-assisted discovery`: `auth_ris` + `firecrawl_justice_portal` with
   `scope.kind=discovered_subset`
4. review findings
5. add or tighten authority mappings and path rules
6. only then consider CH canton/court exploratory slices

## Recommendation summary

If the goal is to move fast without losing control:

- use deterministic slices first for the trusted CH and AT cores
- use AI-assisted preview only for discovery and narrowing
- keep production acceptance tied to reviewed acquisition specs and run-scoped evidence

That gives you a thin-slice start without pretending AI-first exploration is already the
high-precision production path.
