# Hetzner k3s — cluster bootstrap & deploy
> **Platform commands here have moved.** `deploy-stage{1,2,3,8}.sh`,
> `deploy-observability.sh`, `deploy-runners.sh` and the `values/` files now live in
> [research-platform](https://github.com/philipplukas/research-platform) (`scripts/`, `data/`,
> `identity/`, `observability/`). The copies under `infra/hetzner/` are frozen duplicates
> awaiting deletion — see [`infra/hetzner/OWNERSHIP.md`](../../infra/hetzner/OWNERSHIP.md).
> Stages 4 and 5 are still run from this repository.

How to take a **bare Hetzner dedicated server** to a running single-node k3s cluster with
Evidara on it, replacing GCP. This is the bootstrap that was previously undocumented (the
cluster used to be assumed-existing and reached over Tailscale). Companion to
[ADR-0029](../adr/0029-self-hosted-hetzner-runtime.md), [`infra/hetzner/`](../../infra/hetzner/README.md),
and the [cutover runbook](../runbooks/hetzner-cutover.md).

> **Steady state vs bootstrap.** The steps below are the *one-time* manual bootstrap /
> disaster-recovery path. Once the cluster is up, move to **GitOps** (Argo CD) + a **VPN**
> so future changes are git-driven, not hand-typed — see [§Steady state](#steady-state--codify-it).

Reference box: `88.99.26.120` — dedicated server, 8-core i7-6700, 64 GB RAM, 3× 512 GB NVMe.

## 0. Prerequisites

- Hetzner **Robot** access (dedicated servers live in Robot, not the Cloud Console).
- An SSH keypair on your laptop: `ls ~/.ssh/id_ed25519.pub` or `ssh-keygen -t ed25519`.
- `brew install kubectl helm git` on the laptop.

## 1. Reinstall a clean OS (rescue → installimage)

When locked out (e.g. lost VPN/firewall) or starting fresh:

1. **Robot → Rescue tab** → activate **Linux 64-bit** rescue → note the temporary password.
2. **Robot → Reset tab** → "Execute an automatic hardware reset" → boots into rescue (~1–2 min).
3. SSH into rescue (if your laptop cached an old host key: `ssh-keygen -R 88.99.26.120` first):

   ```bash
   ssh root@88.99.26.120        # rescue password
   ```

4. Pre-seed your SSH key so the new system trusts it:

   ```bash
   mkdir -p /root/.ssh
   echo "ssh-ed25519 AAAA... you@host" >> /root/.ssh/authorized_keys
   ```

5. Install Debian non-interactively (RAID 5 across the 3 NVMe, ~952 GB usable). `TERM=xterm`
   avoids "unknown terminal type" on the menu editor:

   ```bash
   export TERM=xterm
   installimage -a -n evidara-k3s -r yes -l 5 \
     -p swap:swap:32G,/boot:ext3:1024M,/:ext4:all \
     -K /root/.ssh/authorized_keys \
     -i /root/.oldroot/nfs/install/../images/Debian-1305-trixie-amd64-base.tar.zst
   ```

   (The image filename is whatever `installimage`'s menu lists under Debian — adjust if it differs.)
6. `reboot`. The box comes up as fresh Debian; RAID resyncs in the background (`cat /proc/mdstat`)
   while the system is fully usable.
7. Reconnect (host key changed again): `ssh-keygen -R 88.99.26.120 && ssh root@88.99.26.120`.

## 2. Install k3s

On the box. `--tls-san` makes the API reachable from your laptop; `--write-kubeconfig-mode`
makes the kubeconfig copyable:

```bash
curl -sfL https://get.k3s.io | INSTALL_K3S_EXEC="--tls-san 88.99.26.120 --write-kubeconfig-mode 644" sh -
k3s kubectl get nodes      # expect: evidara-k3s Ready
```

k3s bundles containerd, flannel CNI, CoreDNS, Traefik ingress, ServiceLB, and the
`local-path` storage provisioner — enough to start without extra installs.

## 3. Point your laptop at the cluster

```bash
git clone git@github.com:philipplukas/evidara.git   # or https:// + token, or: gh repo clone
cd evidara && git checkout <working-branch>

scp root@88.99.26.120:/etc/rancher/k3s/k3s.yaml ~/.kube/evidara-hetzner.yaml
sed -i '' 's/127.0.0.1/88.99.26.120/' ~/.kube/evidara-hetzner.yaml   # macOS sed
export KUBECONFIG=~/.kube/evidara-hetzner.yaml
kubectl get nodes
```

## 4. Deploy Evidara (staged)

All manifests live in [`infra/hetzner/`](../../infra/hetzner/README.md). Run from the repo root:

```bash
export KUBECONFIG=~/.kube/evidara-hetzner.yaml
bash infra/hetzner/deploy-stage1.sh        # MinIO + CloudNativePG Postgres
# stage 2: NATS + OpenSearch
# stage 3: Nessie + Trino (Iceberg lakehouse)
# stage 4: Evidara apps
kubectl -n evidara get pods
```

Once the apps are up, verify the CH Fedlex head of the pipeline (platform-control → NATS →
MinIO → document-intelligence) with the fast-loop canary: see
[CH Fedlex canary — backend wiring & fast-loop](hetzner-ch-fedlex-canary.md).

## Steady state — codify it

The above is bootstrap. The target operating model (see ADR-0029, migration docs):

1. **GitOps with Argo CD** — install once, point an `Application` at the repo; Argo
   reconciles the cluster to git. Stop running `helm install`/`kubectl apply` by hand;
   commit and let Argo sync.
2. **Reproducible provisioning** — codify §1–§2 (NixOS + `nixos-anywhere`, or `k3sup`/Ansible)
   so a full rebuild is one command, not the interactive `installimage` dance.
3. **Private access** — restore a **VPN** (Tailscale/WireGuard) and stop relying on the
   public IP for the API.

## Security follow-ups (do before real use)

- **Firewall the k8s API (6443)** to your IP/VPN — it is currently reachable on the public IP.
- **MinIO / Postgres credentials** → move from values files into pre-created k8s `Secret`s
  (the values in `infra/hetzner/values/` use placeholders).
- **Ingress + TLS** — front the apps with Traefik (bundled) or ingress-nginx + cert-manager;
  don't expose services as bare NodePorts.
