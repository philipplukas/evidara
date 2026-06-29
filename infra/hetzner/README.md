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

> Security follow-up: the k8s API (6443) and, later, the app ingress are exposed on the
> public IP. Once Tailscale (or a firewall) is back, restrict 6443 to your IP. Tracked as
> a hardening TODO — fine for bring-up.

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
