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

```bash
kubectl apply -f infra/hetzner/00-namespace.yaml

# MinIO
helm repo add minio https://charts.min.io/ && helm repo update
helm upgrade --install minio minio/minio -n evidara -f infra/hetzner/values/minio.yaml

# Postgres (CloudNativePG operator, then the cluster)
kubectl apply --server-side -f https://raw.githubusercontent.com/cloudnative-pg/cloudnative-pg/release-1.24/releases/cnpg-1.24.0.yaml
kubectl -n cnpg-system rollout status deploy/cnpg-controller-manager
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

## Stage 5 — real auth (ADR-0020)

`deploy-stage5.sh` puts both apps behind real auth. Idempotent; rebuild the admin and
legal-search-frontend images first (their middleware changed), then:

```sh
BASIC_AUTH_USER=admin BASIC_AUTH_PASS='choose-a-strong-pass' bash infra/hetzner/deploy-stage5.sh
```

- **API keys** — the `evidara-auth` Secret holds a `PLATFORM_CONTROL_OPERATOR_API_KEY` and a
  `LEGAL_SEARCH_API_KEY` (generated once, reused after). Each API enforces `X-API-Key`; the
  matching Next.js middleware (`platform-control/admin`, `legal-search/frontend`) injects the
  key server-side when proxying, so the browser never sees it. Both keys are wired as
  `optional` secret refs — absent key ⇒ API stays open (backward compatible).
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

> **First-rollout check.** Confirm `jetstream_consumer_num_pending` actually resolves in
> Prometheus. The `prometheus-nats-exporter` metric names have moved between versions,
> and an alert on a metric that does not exist is worse than no alert — it looks like one.
