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
- **Front door** — Traefik BasicAuth Middleware + Ingress on the `*.88-99-26-120.nip.io`
  hostnames (admin + search). Rotate the BasicAuth password out-of-band; `deploy-stage5.sh`
  creates `evidara-basicauth` once and preserves it on re-runs:
  `htpasswd -nbB admin 'new-pass' | kubectl -n evidara create secret generic evidara-basicauth --from-literal=users=/dev/stdin ...`
- **Trusted TLS** — cert-manager (v1.20.x) is installed with Let's Encrypt `ClusterIssuer`s
  (`letsencrypt-staging`, `letsencrypt-prod`; see `auth/letsencrypt-issuer.yaml`). To move
  off Traefik's self-signed cert onto a real domain: create A records for
  `admin.evidara.veyo.dev` / `search.evidara.veyo.dev` → `88.99.26.120` (Evidara nests under
  the neutral `veyo.dev` umbrella), then `kubectl apply -f auth/ingress-tls.yaml`
  (staging first, then flip the annotations to
  `letsencrypt-prod`). Port 80 stays public for the HTTP-01 challenge — only 6443 is
  tailnet-locked.

> The frontend reaches its API in-cluster via `NEXT_PUBLIC_API_URL=http://legal-search-api.evidara.svc:8080`
> (the middleware rewrites `/v1/*` there). The old `localhost:3102` dev default ECONNREFUSED'd inside the pod.
