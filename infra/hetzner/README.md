# Evidara on self-hosted Hetzner k3s

Deploy guide for the single-node k3s cluster (`evidara-k3s`, dedicated server) that
replaces GCP — see [ADR-0029](../../docs/adr/0029-self-hosted-hetzner-runtime.md).
Unlike `k8s/gitops/` (which assumes a MacConfig-managed platform with external stores),
this tree is **self-contained**: it deploys the stores in-cluster too, because we own the
whole node.

> Run everything from your **laptop** with `kubectl` + `helm` pointed at the cluster.
> Apply in stages; verify each before the next.

## Stack

| Layer | Component | How |
|---|---|---|
| Storage | **MinIO** (S3) | helm `minio/minio` |
| Database | **Postgres** (CloudNativePG) | operator + `Cluster` CR |
| Messaging | **NATS JetStream** | helm `nats/nats` |
| Search | **OpenSearch** | helm `opensearch/opensearch` |
| Lakehouse catalog | **Nessie** (Iceberg REST, git-like) | helm `nessie/nessie`, Postgres-backed |
| Lakehouse query | **Trino** | helm `trino/trino` |
| Apps | Evidara services | `k8s/gitops` overlay (adapted) |
| Observability | **Prometheus + Alertmanager + Grafana** | helm `prometheus-community/kube-prometheus-stack` |
| Identity | **Zitadel** (OIDC provider) | helm `zitadel/zitadel`, Postgres-backed — ADR-0038 |

Stateful services use the k3s built-in `local-path` storage class and the RAID-5 root.

## Prerequisites (laptop)

```bash
brew install kubectl helm        # macOS
# kubeconfig from the cluster (k3s was installed with --tls-san 88.99.26.120):
scp root@88.99.26.120:/etc/rancher/k3s/k3s.yaml ~/.kube/evidara-hetzner.yaml
sed -i '' 's/127.0.0.1/88.99.26.120/' ~/.kube/evidara-hetzner.yaml   # macOS sed
export KUBECONFIG=~/.kube/evidara-hetzner.yaml
kubectl get nodes                # expect: evidara-k3s Ready
```

> **k8s API (6443) is locked to Tailscale.** The node runs Tailscale (`tailscale up`,
> hostname `evidara-k3s`, tailnet IP `100.122.182.54`), and an nftables rule
> (`/etc/nftables-evidara.conf`, persisted by `evidara-fw.service`) drops 6443 on the
> public NIC `enp0s31f6`. In-cluster (`cni0`/`flannel`), tailnet (`tailscale0`), and
> loopback paths are unaffected. Point your kubeconfig at the tailnet IP:
> `sed -i '' 's#88.99.26.120:6443#100.122.182.54:6443#' ~/.kube/evidara-hetzner.yaml`
> (the API cert carries both SANs via `/etc/rancher/k3s/config.yaml` `tls-san`). SSH (22)
> and the app ingress (80/443) remain public — a public app domain + trusted TLS is the
> next hardening step.

## Stage 1 — foundation (storage + database)

**MinIO root credentials first** — `values/minio.yaml` sets `existingSecret: minio-root`
and carries no password, so the Secret must exist before the chart is installed. The
password is generated inline and never printed or committed:

```bash
NS=evidara
kubectl apply -f infra/hetzner/00-namespace.yaml
kubectl -n $NS create secret generic minio-root \
  --from-literal=rootUser=evidara \
  --from-literal=rootPassword="$(openssl rand -hex 24)"
```

```bash
# MinIO
helm repo add minio https://charts.min.io/ && helm repo update
helm upgrade --install minio minio/minio -n evidara -f infra/hetzner/values/minio.yaml

# Postgres (CloudNativePG operator, then the cluster)
kubectl apply --server-side -f https://raw.githubusercontent.com/cloudnative-pg/cloudnative-pg/release-1.24/releases/cnpg-1.24.0.yaml
kubectl -n cnpg-system rollout status deploy/cnpg-controller-manager
```

### Per-workload MinIO service accounts

**Root is administrative only.** No workload authenticates to MinIO with it. Each one has
its own MinIO user, scoped by an IAM policy to the buckets and actions its code actually
uses, delivered in its own Kubernetes Secret. Provision them before `deploy-stage4.sh`
and before applying `postgres-cluster.yaml` (which references `cnpg-minio-backup`):

```bash
bash infra/hetzner/provision-minio-users.sh    # idempotent; passwords generated, never printed
bash infra/hetzner/verify-minio-scoping.sh     # the allow/deny assertions — must be all PASS
```

The source of truth is [`minio-policies/accounts.json`](minio-policies/accounts.json) plus
the policy documents beside it. Both scripts and the CI guard
(`scripts/check_hetzner_minio_credentials.py`) read that one file.

| MinIO user | Kubernetes Secret | Workloads | `evidara-raw-artifacts` | `evidara-lakehouse` | `evidara-pg-backups` |
|---|---|---|---|---|---|
| `platform-control` | `evidara-s3-platform-control` | `platform-control-api`, `platform-control-retention-sweep` | **write + delete** (no read) | denied | denied |
| `di-consumer` | `evidara-s3-di-consumer` | `di-consumer` | read | **read/write** under `canonical/` | denied |
| `document-service` | `evidara-s3-document-service` | `document-service` | denied | **read** under `canonical/` | denied |
| `trino` | `evidara-s3-trino` | Trino coordinator + worker | denied | **read/write** | denied |
| `cnpg-backup` | `cnpg-minio-backup` | CloudNativePG `barmanObjectStore` | denied | denied | **read/write** |
| — | — | `projection-bridge` | **no credential at all** | | |

Why each scope is what it is, from the code rather than from guesswork:

- **platform-control** implements only `store_page_payload`, `store_bundle_manifest` and
  `delete_blob` (`platform-control/src/platform_control/services/artifact_store.py`) — it
  never reads an artifact back, so it has no `s3:GetObject`. **If you add a read path,
  widen `minio-policies/platform-control.json` in the same PR**; `verify-minio-scoping.sh`
  asserts the read is denied today, so it will tell you.
- **di-consumer** reads bundles from `evidara-raw-artifacts`
  (`document-intelligence/src/document_intelligence/ingest/loaders.py`) and writes the
  Delta surfaces named by `DI_PUBLISHED_*_URI` / `DI_PROCESSING_MANIFESTS_URI` in
  `apps/configmap.yaml`, all under `s3://evidara-lakehouse/canonical/`.
- **document-service** only reads those same surfaces back
  (`document_intelligence/service/store.py::DeltaPublishedDocumentStore`).
- **trino** queries Iceberg with `default-warehouse-dir=s3://evidara-lakehouse`
  (`values/trino.yaml`) and touches nothing else.
- **projection-bridge** makes no object-storage call at all — it consumes NATS and POSTs
  HTTP. It held the shared root key until #813 only because it took `evidara-app-secrets`
  via `envFrom`.

`evidara-app-secrets` now carries **only** `PLATFORM_CONTROL_DATABASE_URL`. It is mounted
by every platform-control workload; anything put in it is held by all of them at once,
which is how one credential became five workloads' worth of blast radius.

Verify one account by hand, the way ADR-0038 §2 first did for `cnpg-backup`:

```bash
# using the account's own credential, not root
mc ls v/evidara-pg-backups/     # allowed
mc ls v/evidara-raw-artifacts/  # MUST be "Access Denied"
mc ls v/evidara-lakehouse/      # MUST be "Access Denied"
```

Cutover from the previous shared-root arrangement, including rollback:
[docs/runbooks/minio-least-privilege-cutover.md](../../docs/runbooks/minio-least-privilege-cutover.md).

### Rotating the MinIO root credential

**MinIO encrypts its IAM data with the root credential.** Rotating root without telling
MinIO the previous value orphans **every** IAM user — `platform-control`, `di-consumer`,
`document-service`, `trino`, `cnpg-backup` and `console` — and Postgres backups plus the
whole pipeline start failing with auth errors that look nothing like the cause.
Pass the old credential for exactly one deploy so MinIO re-encrypts:

```bash
NS=evidara
OLD_U=$(kubectl -n $NS get secret minio-root -o jsonpath='{.data.rootUser}' | base64 -d)
OLD_P=$(kubectl -n $NS get secret minio-root -o jsonpath='{.data.rootPassword}' | base64 -d)

kubectl -n $NS create secret generic minio-root \
  --from-literal=rootUser=evidara \
  --from-literal=rootPassword="$(openssl rand -hex 24)" \
  --dry-run=client -o yaml | kubectl apply -f -

helm upgrade --install minio minio/minio -n $NS -f infra/hetzner/values/minio.yaml \
  --set environment.MINIO_ROOT_USER_OLD="$OLD_U" \
  --set environment.MINIO_ROOT_PASSWORD_OLD="$OLD_P" --wait
unset OLD_U OLD_P
```

Confirm both users survived, then re-run the same `helm upgrade` **without** the two
`--set` flags so the old credential stops being passed:

```bash
POD=$(kubectl -n $NS get pod -l app=minio -o jsonpath='{.items[0].metadata.name}')
kubectl -n $NS exec $POD -- sh -c "mc --config-dir /tmp/c alias set r http://localhost:9000 \
  \$MINIO_ROOT_USER \$MINIO_ROOT_PASSWORD && mc --config-dir /tmp/c admin user list r"
# MUST list platform-control, di-consumer, document-service, trino, cnpg-backup, console
```

**Rotating root does not rotate the workload credentials, and no longer needs to.** They
are separate MinIO users; only their IAM records were re-encrypted. Re-run the
verification to prove they survived — nothing else, and no app restart:

```bash
bash infra/hetzner/verify-minio-scoping.sh
```

If a user *was* orphaned (the `admin user list` above is short), re-provision just that
one and restart only its workloads — see the cutover runbook:

```bash
bash infra/hetzner/provision-minio-users.sh <user>
```

Then the cluster:

```bash
kubectl apply -f infra/hetzner/postgres-cluster.yaml
```

Verify:
```bash
kubectl -n evidara get pods            # minio + evidara-pg-1 Running
kubectl -n evidara get cluster evidara-pg   # Cluster in healthy state
```

The CNPG cluster auto-creates secret `evidara-pg-app` (user/password/dbname) and a
read-write service `evidara-pg-rw`. platform-control's DB URL becomes:
`postgresql+asyncpg://<user>:<pass>@evidara-pg-rw:5432/platform_control`.

## Stage 2 — messaging + search (next)

NATS JetStream + OpenSearch via helm. Values land here as we get there.

## Stage 3 — lakehouse (Iceberg + Nessie + Trino)

Nessie (Postgres-backed REST catalog) + Trino (coordinator + worker) reading Iceberg on
MinIO. The DI pipeline writes Iceberg via PyIceberg → Nessie. See the lakehouse ADR.

## Stage 4 — Evidara apps

Adapt the `k8s/gitops` overlay to this cluster: plain k8s `Secret`s (no Vault/ESO here),
in-cluster store endpoints, k3s `traefik` ingress (or swap to nginx).

`apps/configmap.yaml` wires platform-control onto the real self-hosted backends
(`event_publisher_backend=nats`, `artifact_store_backend=s3`/MinIO) so an admin-launched run
publishes the `evidara.artifact-bundle-available` event + artifact that `di-consumer` reads.
Verify the head of that chain with the CH Fedlex fast-loop canary — backend coordinate table
and operator procedure in
[`docs/setup/hetzner-ch-fedlex-canary.md`](../../docs/setup/hetzner-ch-fedlex-canary.md).

> **Search index bootstrap.** On startup `legal-search-api` idempotently ensures the OpenSearch
> `documents` index exists (canonical mapping from `legal-search/api/src/core/opensearch/`) and
> that the `documents-read` (search) and `documents-write` (projections) aliases resolve to the
> **same** physical index. Without this both aliases would diverge and projected documents would
> never surface in search. Non-destructive and safe to re-run; set
> `OPENSEARCH_BOOTSTRAP_ON_STARTUP=false` on the deployment if a versioned cutover manages the
> aliases out-of-band (see `docs/runbooks/projection-reindex-backfill.md`).

### Rolling out a newer build

Bump **two** files to the same commit SHA — `apps/kustomization.yaml` (`images:`, which covers
the six app images) and `apps/migrate-job.yaml` (which the `images:` transformer deliberately
does not reach, because the Job is applied on its own before the apps roll). The long comment
at the top of `apps/kustomization.yaml` explains how to choose a SHA and records what each
rollout changed.

`scripts/check_hetzner_image_pins.py` fails the build if those two drift apart — it runs in
pre-commit and in the `docs-and-contracts` workflow, so this is not something to remember.
The guard exists because the drift already reached production: the migrate Job sat at
6e1816a7 while the apps rolled at da39660d, so revision `20260714_0021` was never applied and
`jurisdictions` had no `level` column under code that maps it. **The Job reported success the
whole time** — from its own older image there was nothing left to apply — so the only visible
symptom was `UndefinedColumn` at request time.

Always confirm the migration actually landed rather than trusting the Job's exit status:

```sh
kubectl -n evidara exec evidara-pg-1 -- \
  psql -U postgres -d platform_control -tAc 'select version_num from alembic_version;'
```

It must match the newest revision in `platform-control/alembic/versions/`.

## Stage 5 — real auth (ADR-0020)

`deploy-stage5.sh` puts both apps behind real auth. Idempotent; rebuild the admin and
legal-search-frontend images first (their middleware changed), then:

```sh
BASIC_AUTH_USER=admin BASIC_AUTH_PASS='choose-a-strong-pass' bash infra/hetzner/deploy-stage5.sh
```

- **API keys** — the `evidara-auth` Secret holds a `PLATFORM_CONTROL_OPERATOR_API_KEY` and a
  `LEGAL_SEARCH_API_KEY` (generated once, reused after). Each API enforces `X-API-Key`; the
  matching Next.js middleware (`platform-control/admin`, `legal-search/frontend`) injects the
  key server-side when proxying, so the browser never sees it.
  **The Secret is required, and both APIs fail closed.** This used to read "absent key ⇒ API
  stays open (backward compatible)" — an unmounted Secret silently served the whole control
  plane and search API to anyone who could reach them, and looked identical to a working
  deployment. Now:
  - The secret refs are **not** `optional`, so a pod without `evidara-auth` refuses to start.
  - If a keyless process does start anyway, every protected route returns **503**
    (`Authentication is not configured`), and platform-control logs a `CRITICAL` line at boot.
  - Health/readiness endpoints stay reachable either way, so an unconfigured pod is still
    diagnosable.
  - The keyless path still exists for local development, but must be requested by name:
    `PLATFORM_CONTROL_AUTH_DEV_ALLOW_UNAUTHENTICATED=1` / `AUTH_DEV_ALLOW_UNAUTHENTICATED=1`.
    Never set either in this cluster.
  Run `deploy-stage5.sh` before `kubectl apply -k apps/`.
- **Front door** — Traefik BasicAuth Middleware + Ingress on the real hostnames
  `admin.evidara.veyo.dev` / `search.evidara.veyo.dev` (admin + search; the old
  `*.88-99-26-120.nip.io` ingress has been retired). Rotate the BasicAuth password
  out-of-band; `deploy-stage5.sh` creates `evidara-basicauth` once and preserves it on re-runs:
  `htpasswd -nbB admin 'new-pass' | kubectl -n evidara create secret generic evidara-basicauth --from-literal=users=/dev/stdin ...`
- **Trusted TLS** — live. cert-manager (v1.20.x) + Let's Encrypt `ClusterIssuer`s
  (`letsencrypt-staging`, `letsencrypt-prod`; see `auth/letsencrypt-issuer.yaml`) issue trusted
  certs for both hosts via the HTTP-01 challenge (`auth/ingress-tls.yaml`, annotation pinned to
  `letsencrypt-prod`). Evidara nests under the neutral `veyo.dev` umbrella; A records
  `admin.evidara.veyo.dev` / `search.evidara.veyo.dev` → `88.99.26.120` (IPv4-only — no AAAA,
  the node doesn't serve 443 over IPv6). To reissue on a new host, apply with the
  `letsencrypt-staging` annotation first to dodge rate limits, then flip to `letsencrypt-prod`.
  Port 80 stays public for the HTTP-01 challenge — only 6443 is tailnet-locked.

> The frontend reaches its API in-cluster via `NEXT_PUBLIC_API_URL=http://legal-search-api.evidara.svc:8080`
> (the middleware rewrites `/v1/*` there). The old `localhost:3102` dev default ECONNREFUSED'd inside the pod.

## Stage 6 — self-hosted CI runners (ADR-0029)

Heavy CI jobs exhausted the GitHub-hosted Actions credit limit, so both runner pools
run on this (near-idle) node via GitHub's **Actions Runner Controller** (ARC /
`gha-runner-scale-set`). The two scale sets are named to match the repo Actions
variables and every workflow's `runs-on:`:

| Pool | Scale set (= `runs-on` label) | Repo variable | Serves |
|---|---|---|---|
| Light | `evidara-light` | `LIGHT_RUNNER_SCALE_SET` | `check-title`, `contract-validation` (both **required checks**), terraform, CD control-plane |
| Heavy | `evidara-heavy-v2` | `HEAVY_RUNNER_SCALE_SET` | e2e/Playwright smoke, document-intelligence heavy jobs |

Docker/buildx image builds (`runtime-images.yml`) deliberately stay GitHub-hosted —
no Docker-in-Docker on-cluster.

### The heavy pool runs a custom image

The stock `ghcr.io/actions/actions-runner` image carries no browser system libraries,
so Playwright's Chromium dies with `libnspr4.so: cannot open shared object file`. Every
workflow guards its `playwright install-deps` step with `if: runner.environment ==
'github-hosted'`, because the runner container has no root and `install-deps` needs
apt — self-hosted runners are expected to have the deps baked in.

`runners/Dockerfile.heavy` is what makes that true. It is built and pushed to
`ghcr.io/philipplukas/evidara-runner-heavy` by `.github/workflows/runner-image.yml`
(GitHub-hosted — building it on the pool it produces would be circular). That workflow
launches Chromium as the unprivileged `runner` user before pushing, so a missing
library fails the build instead of a nightly smoke four days later.

Two things to know when changing it:

- **The GHCR package must be public.** ARC pulls it with no `imagePullSecret`, like
  every other `ghcr.io/philipplukas/evidara-*` image. A fresh package defaults to
  private; flip it once, after the first push to `main`.
- **`PLAYWRIGHT_VERSION` tracks `@playwright/test`** in `legal-search/frontend/package.json`.
  It only pins the OS-level deps — browsers are still installed per job and cached
  under `~/.cache/ms-playwright`.

No redeploy is needed to roll out a new image: runner pods are ephemeral and created
per job, and the `:latest` tag means `imagePullPolicy` defaults to `Always`, so the
next heavy job pulls it.

```sh
# One-time: create a classic PAT with the `repo` scope (ARC also accepts a GitHub App):
#   https://github.com/settings/tokens/new?scopes=repo&description=evidara-arc-runners
export GITHUB_RUNNER_PAT=ghp_xxx
bash infra/hetzner/deploy-runners.sh
```

The script (idempotent) installs the ARC controller into `arc-systems`, stores the
credential as the `evidara-runner-github` Secret in `arc-runners`, and `helm upgrade
--install`s both scale sets from `runners/values-{light,heavy}.yaml`. Runners are
**ephemeral, idle-to-zero** (`minRunners: 0`) so they cost nothing at rest and
self-recycle each job. Verify:

```sh
kubectl -n arc-systems get pods          # controller + one *-listener pod per scale set
kubectl -n arc-runners get autoscalingrunnerset   # both scale sets, CURRENT RUNNERS 0 at rest
gh api repos/philipplukas/evidara/actions/runners --jq '.runners[].name'
```

> The listener pods live in `arc-systems` (the controller's namespace), not `arc-runners`.
> `arc-runners` holds only ephemeral job pods, so it is legitimately **empty at rest** —
> `minRunners: 0`. An empty `arc-runners` is not a runner outage; check `arc-systems`.

> **These pools own the required checks.** If they are offline, no PR can merge —
> `check-title` + `contract-validation` never start. That was the CI blocker after the
> GKE cluster (which hosted the old ARC pools) was decommissioned.

## Stage 7 — observability (ADR-0032)

Until this stage the cluster had **no metrics and no alerting**. Every failure in the
June/July outage (#549/#550/#551) was silent: the OpenSearch document index was missing
entirely, search returned an empty page for every query, and every pod stayed `Running`,
`1/1 Ready`, zero restarts the whole time. Liveness probes answer *"is the process
alive"*; nothing answered *"is work actually flowing"*.

```sh
bash infra/hetzner/deploy-observability.sh
```

Idempotent. Installs `kube-prometheus-stack` (Prometheus + Alertmanager + Grafana) into a
new `monitoring` namespace, re-applies the NATS release to add the JetStream exporter
sidecar, then applies the Evidara scrape targets, alert rules, and the **pipeline funnel
dashboard** — one number per stage:

```
runs launched → artifacts captured → DI messages processed → document.processed
  → documents indexed → docs searchable now → search queries → ...with hits
```

A leak between any two stages is a step change you cannot miss; an outage is a zero.

Day-one alerts include `documents-read` failing to resolve (the #549 total outage,
previously 100% undetected), read/write alias divergence (#551), a zero-result rate above
95%, and DI processing messages while zero documents reach OpenSearch.

Full deploy/verify/receiver-wiring guide:
[`docs/setup/hetzner-observability.md`](../../docs/setup/hetzner-observability.md).

> **Alertmanager has no external receiver out of the box** — alerts land in its UI and
> nobody's phone rings. Wiring a Slack webhook is a one-value change; the credential is
> deliberately the operator's, not the repo's. See the setup guide.

> **First-rollout check.** Confirm `nats_consumer_num_pending` actually resolves in
> Prometheus. The `prometheus-nats-exporter` metric names have moved between versions,
> and an alert on a metric that does not exist is worse than no alert — it looks like one.

### Bouncing NATS (what the consumers do) — #722

`di-consumer` and `projection-bridge` retry the broker **forever**
(`max_reconnect_attempts=-1`). Bouncing NATS — a helm upgrade, a node drain, a transient
network fault — no longer kills them; they reconnect and resume consuming on their own.

They used to die. Neither ever configured a reconnect policy, so both inherited nats-py's
default of 60 attempts at 2s. Any outage past ~2 minutes expired it, the client closed the
connection, and `fetch()` raised `ConnectionClosedError` straight out of the run loop. The
pods restarted (restartPolicy defaults to `Always`) but the local docker-compose stack did
not, and either way the *symptom* was a pipeline stalled at `canonical_ready=0` — which
reads as a document-processing regression, not a dead consumer. That misdiagnosis is the
reason this is written down.

The two probes now answer different questions, and you need both to read the situation:

| Probe | Question | During a broker outage |
|---|---|---|
| `/health` (liveness) | Is the process alive? | **200** — it is healthy and correctly retrying |
| `/ready` (readiness) | Can it reach the broker? | **503**, with `broker_connected: false` and a reason |

So `kubectl get pods -n evidara` showing `di-consumer 0/1 Running` with no restarts means
*the broker is unreachable*, not that the consumer is broken. Check NATS first. If the pod
is also restarting, the connection closed unrecoverably — the consumer exits non-zero on
purpose so the restart policy takes over.

Publishing is the mirror image: platform-control's dispatch path answers an operator over
HTTP, so it does **not** retry. It bounds the connect at
`PLATFORM_CONTROL_NATS_CONNECT_TIMEOUT_SECONDS` (default 5s) and fails the rest of the
batch immediately for a 30s cooldown, so a run against a down broker returns a 502 naming
the cause in seconds and records the run `failed` (#707) rather than hanging for minutes.

## Stage 8 — identity provider (ADR-0038 step 2)

Zitadel, self-hosted OIDC, on `https://id.evidara.veyo.dev`. This stage **stands it up
and stops**. Nothing authenticates against it: both UIs remain behind the shared
BasicAuth password, and ADR-0038 §8 orders the wiring (operator schema → assertion seam
→ Auth.js login → role enforcement) strictly after this. §8 step 2's words are that
this has to be *boring* before anything depends on it.

```sh
# Prereq: DNS A record id.evidara.veyo.dev -> 88.99.26.120 (IPv4 only), resolving.
bash infra/hetzner/deploy-stage8.sh
```

Idempotent. It creates a dedicated `zitadel` Postgres role and database in the existing
CNPG cluster, generates the two Secrets it needs (`zitadel-db` holding the DSN,
`zitadel-masterkey` holding the 32-byte encryption key) **once**, and installs the
pinned chart. Re-runs never mint new credentials over a working instance — the same
create-once rule as `evidara-auth` in Stage 5.

- **No credential is committed.** `values/zitadel.yaml` contains only Secret *names*;
  `scripts/check_hetzner_zitadel.py` fails the build if a password, DSN or masterkey
  ever appears in it. (`values/minio.yaml` carried a placeholder root password on `main`
  that was the live credential — #792, fixed; `scripts/check_hetzner_minio_credentials.py`
  is the equivalent guard, and since #813 it also fails a workload that authenticates to
  MinIO as root at all.)
- **Its own Postgres role, unlike Nessie.** Nessie shares the `platform_control` owner;
  Zitadel does not. An IdP is the highest-value target in the runtime (ADR-0038 §2b),
  and a leak of its DSN must not also expose every run, approval and operator row.
- **Backups needed no new configuration.** barman archives the whole instance, so the
  `zitadel` database joined the Stage 1 backup path the moment it existed. What is not
  automatic is the *proof* — and the masterkey is a separate backup artifact a Postgres
  restore cannot recover.
- **Two Ingresses, one certificate.** Zitadel v4 serves its login UI from a separate
  deployment under `/ui/v2/login`. Both Ingresses carry `tls:` (a Traefik ingress
  without it never answers on 443) but only one carries the cert-manager annotation, or
  the two contend for a single Certificate object.
- **Not behind `evidara-basicauth`, deliberately.** A login page you need the shared
  password to reach cannot replace the shared password.

Operations, the restore drill that gates this step, and the break-glass procedure:
[`docs/runbooks/zitadel-identity-provider.md`](../../docs/runbooks/zitadel-identity-provider.md).

> **The offsite-backup gate is real.** MinIO's backup PVC is on the same disk as the
> Postgres PVC, so a disk loss takes the IdP and its backup together. ADR-0038 §2b makes
> an offsite destination a prerequisite **before Zitadel holds real user credentials** —
> deploying it empty is fine; onboarding people into it is not.
