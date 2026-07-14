# Hetzner CH Fedlex canary — backend wiring & fast-loop procedure

How platform-control publishes events and stores artifacts on the **real** self-hosted
backends (NATS JetStream + MinIO) that document-intelligence consumes, and how to run the
`scripts/ch-fedlex-fast-loop.sh` canary against the Hetzner cluster.

Companion to [ADR-0029](../adr/0029-self-hosted-hetzner-runtime.md),
[`infra/hetzner/`](../../infra/hetzner/README.md), and
[`docs/setup/hetzner-k3s.md`](hetzner-k3s.md). This is the **head of the CH-data-to-search-UI
chain** (Stream D): a run launched from the admin panel only feeds downstream once
platform-control emits on these backends. The platform default is
`event_publisher_backend=noop` + a local artifact store — a run then succeeds but emits
nothing.

## 1. Backend wiring (already in the cluster manifests)

The self-hosted backends are selected by env, sourced from
[`infra/hetzner/apps/configmap.yaml`](../../infra/hetzner/apps/configmap.yaml) (non-secret
coordinates) and the `evidara-app-secrets` Secret created by
[`infra/hetzner/deploy-stage4.sh`](../../infra/hetzner/deploy-stage4.sh) (MinIO credentials).

| Setting | Value | Source |
|---|---|---|
| `PLATFORM_CONTROL_EVENT_PUBLISHER_BACKEND` | `nats` | configmap |
| `PLATFORM_CONTROL_NATS_SERVERS` | `nats://nats.evidara.svc:4222` | configmap |
| `PLATFORM_CONTROL_ARTIFACT_STORE_BACKEND` | `s3` | configmap |
| `PLATFORM_CONTROL_S3_ENDPOINT_URL` | `http://minio.evidara.svc:9000` | configmap |
| `PLATFORM_CONTROL_S3_REGION` | `us-east-1` | configmap |
| `PLATFORM_CONTROL_RAW_ARTIFACT_BUCKET` | `evidara-raw-artifacts` | configmap |
| `PLATFORM_CONTROL_S3_ACCESS_KEY_ID` / `..._SECRET_ACCESS_KEY` | `evidara` / MinIO root pw | `evidara-app-secrets` |
| `PLATFORM_CONTROL_RUN_DISPATCH_BACKEND` | `inline` | configmap |

The NATS subjects are **not** pinned in the configmap; platform-control uses its defaults
(`nats_raw_artifact_subject=evidara.raw-artifact-available`,
`nats_artifact_bundle_subject=evidara.artifact-bundle-available` — see
[`platform-control/src/platform_control/config.py`](../../platform-control/src/platform_control/config.py)).
Both fall under the `evidara.>` stream created by
[`infra/hetzner/nats-stream-init.job.yaml`](../../infra/hetzner/nats-stream-init.job.yaml).

### Producer ↔ consumer coordinate check

The output contract of this stream is the `artifact-bundle-available` event + its artifact
payload in MinIO — the input contract for DI's `di-consumer`. The coordinates line up:

| Coordinate | platform-control (producer) | document-intelligence (consumer) | Match |
|---|---|---|---|
| NATS servers | `nats://nats.evidara.svc:4222` | `nats://nats.evidara.svc:4222` (`NATS_SERVERS`) | ✅ |
| JetStream stream | `EVIDARA` (publishes `evidara.artifact-bundle-available`, which matches `evidara.>`) | `EVIDARA` (`--stream` default) | ✅ |
| Bundle subject | `evidara.artifact-bundle-available` (`nats_artifact_bundle_subject` default) | `evidara.artifact-bundle-available` (`--bundle-subject` default) | ✅ |
| MinIO endpoint | `http://minio.evidara.svc:9000` (`PLATFORM_CONTROL_S3_ENDPOINT_URL`) | `http://minio.evidara.svc:9000` (`DI_S3_ENDPOINT_URL`) | ✅ |
| Bucket | writes `s3://evidara-raw-artifacts/…` and puts that URI in the event's `manifest_ref.storage_ref` | resolves the bucket from the `s3://…` URI (`DispatchingBundleLoader` → `S3BundleLoader`) | ✅ |

Consumer defaults live in
[`document-intelligence/src/document_intelligence/jobs/nats_consumer.py`](../../document-intelligence/src/document_intelligence/jobs/nats_consumer.py);
the `di-consumer` Deployment launches it with only `--servers "$NATS_SERVERS"`, so the
stream/subject defaults apply. The MinIO bucket alignment is **by-URI**: platform-control's
`S3ArtifactStore` returns an `s3://evidara-raw-artifacts/<key>` storage ref, which travels in
the bundle event; DI parses the bucket out of that URI and reaches it via `DI_S3_ENDPOINT_URL`.
No separate bucket env has to agree — only the MinIO endpoint, which does.

> If you rename the bucket, the NATS subjects, or the MinIO service, change **both** sides:
> the configmap (producer) and the `di-consumer` command / `DI_S3_*` env (consumer).

## 2. Run the fast-loop canary against Hetzner

The canary (`scripts/ch-fedlex-fast-loop.sh`) drives a narrow CH Fedlex preview
(hardcoded `jurisdiction_id=jur_ch_federal`, `authority_id=auth_fedlex`, overlay `ch`,
template `fedlex_sparql_constitution_de`) through platform-control and asserts the content
and downstream signals, emitting a single `verdict`.

Its default mode targets **GCP Cloud Run** (`gcloud` + an impersonated identity token). For
the self-hosted cluster there is no Cloud Run and platform-control enforces `X-API-Key`
(the `PLATFORM_CONTROL_OPERATOR_API_KEY` from the `evidara-auth` Secret, deploy-stage5). Pass
`--api-key` (or export `EVIDARA_PLATFORM_CONTROL_API_KEY`) to switch the loop into
**self-hosted mode**: it skips `gcloud`/token minting and authenticates with `X-API-Key`
against an explicit `--pc-url`.

```bash
export KUBECONFIG=~/.kube/evidara-hetzner.yaml

# 1. Reach the private platform-control API from your laptop.
kubectl -n evidara port-forward svc/platform-control-api 8080:8080 &

# 2. Read the operator key the API enforces.
OPERATOR_KEY="$(kubectl -n evidara get secret evidara-auth \
  -o jsonpath='{.data.PLATFORM_CONTROL_OPERATOR_API_KEY}' | base64 -d)"

# 3. Reach legal-search too — the indexed-language gate reads the search projection.
kubectl -n evidara port-forward svc/legal-search-api 3102:3000 &

# 4. Run the canary. --env is only a label here (no Cloud Run lookup happens).
scripts/ch-fedlex-fast-loop.sh \
  --pc-url http://localhost:8080 \
  --ls-url http://localhost:3102 \
  --api-key "$OPERATOR_KEY" \
  --env hetzner \
  --json
```

`--ls-url` is required for the **indexed-language gate** (#572): without it the loop cannot
read back the `language` facet it just wrote and reports `indexed_language_checked: 0` +
`verdict=pipeline_pass_content_suspect`. That is deliberate — the bug this gate exists for
(the German Federal Constitution indexed as `language: it`) passed every raw-body check, so
"unverified" must not read as "fine".

Add `--dry-run` first to print the resolved settings and confirm the URL/auth without
mutating anything. Self-hosted mode is triggered by a **non-empty** `--api-key`; if the
`evidara-auth` Secret is absent (API left open) pass any placeholder key together with
`--pc-url` — an open API ignores the `X-API-Key` header, and the non-empty value is only
what routes the loop away from the GCP path.

### Verdict gates

The loop prints a `verdict` (also in `summary.json` / the evidence markdown). Meaning:

| `verdict` | Meaning | What passed / failed |
|---|---|---|
| `pass` | Full end-to-end success | Provider capture, DI `accepted`/`processing`/`canonical_ready`, `document.processed` lifecycle, **and** content-quality gates (text/html, Fedlex `…​.html` URL, `Bundesverfassung` title, ≥3 `Art.` occurrences, ≥10 KB body, German markers `Abs.`/`Bund`/`Recht`, and the indexed `language` facet matching the template's language) all held. |
| `provider_failed` | Acquisition failed | No `text/html` captured, no captured resources, or no raw artifacts. |
| `downstream_failed` | Publish/consume seam broke | Provider captured, but DI never reported `accepted`/`processing`/`canonical_ready` or no `document.processed` lifecycle event arrived — i.e. the NATS/MinIO hop did not complete. |
| `pipeline_pass_content_suspect` | Flowed but content is thin, or the indexed language is wrong | Lifecycle completed but the title/URL/article-density/length/language gates did not all hold. |

#### The language gates

Two separate checks, and the difference matters (#572):

| Check | What it proves |
|---|---|
| `body_lang_hint_ok` | The **raw artifact body** reads as German (`Abs.`/`Bund`/`Recht`). Says nothing about how the document is indexed — it reported `1` for the run that indexed the Bundesverfassung as Italian. |
| `indexed_language_ok` | The **search facet** `language` on every `document.processed` document of this run equals the template's language (`fedlex_sparql_constitution_de` → `de`), read back from `GET {legal-search}/v1/documents/{id}`. This is the gate that protects the facet users and agents filter on. |

`lang_agreement_ok` is now the AND of the two, so a `1` means both held.

The script **exits non-zero unless `verdict=pass`**.

`downstream_failed` is the signal to check this stream's wiring: confirm `di-consumer` is
running and subscribed (`kubectl -n evidara logs deploy/di-consumer`), that the `EVIDARA`
stream exists (`nats-evidara-stream-init` Job completed), and that MinIO holds the bundle
under `evidara-raw-artifacts`.

**Note the counters are reported, not inferred.** `accepted_count` / `processing_count` /
`canonical_ready_count` / `processed_count` are read back from platform-control, and DI never
calls platform-control itself — `di-consumer` only publishes to NATS. The
[`projection-bridge`](../../document-intelligence/src/document_intelligence/jobs/projection_bridge_consumer.py)
Deployment is what POSTs those events to platform-control's `/v1/di/events/*` endpoints. So a
run can process perfectly, index into OpenSearch, and *still* come back `downstream_failed` if
the bridge is down or unauthorized (#550). When the pipeline visibly worked but the counters
are 0, check the bridge before you suspect DI:

```bash
kubectl -n evidara logs deploy/projection-bridge | grep -E 'projection_forward_failed|AuthForwardError'
```

An `AuthForwardError` there means `PLATFORM_CONTROL_OPERATOR_API_KEY` is missing from the
`evidara-auth` secret (or does not match platform-control's) — the callbacks 401. They are
retried rather than dropped, so fixing the key drains the backlog.

## 3. Integration milestone

`verdict=pass` end-to-end is the definition of done for the whole CH-data-to-search-UI set
(Streams A/B/C + this Stream D). The backends are wired and the coordinates verified; the
**live** canary run returning `pass` is gated on the sibling streams (#522/#523/#524) being
live in the same cluster. Record the evidence bundle (`--copy-evidence` writes to
[`docs/runbooks/evidence/`](../runbooks/evidence/)) once it goes green.
