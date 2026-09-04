# Runbook: Hetzner cutover (GCP → self-hosted)

Owner: Platform team
Last reviewed: 2026-07-01
Last verified: Not yet verified
Applies to: dev, staging, prod

Step-by-step for ADR-0029 **Slice 6** — bringing Evidara up on the self-hosted Hetzner
cluster and retiring GCP. Slices 1–5 are done in-repo (NATS, MinIO/S3, k8s manifests);
this runbook is the operator sequence that uses them.

> Order matters: stores → secrets → images → migrate → deploy → validate → destroy.
> Do **staging first** (it is the preferred-first environment), prove it, then prod.

## 0. Prerequisites (one-time)

Owned by the platform (MacConfig) / your cluster, **not** by Evidara manifests:

- [ ] Kubernetes cluster reachable on Hetzner (per the MacConfig platform contract).
- [ ] Namespaces `evidare-dev` / `evidare-staging` / `evidare-prod` exist.
- [ ] `shared-vault` ClusterSecretStore wired (External Secrets Operator installed).
- [ ] Ingress: `nginx` IngressClass + cert-manager `letsencrypt-prod` ClusterIssuer.
- [ ] Backing stores reachable in-cluster (or external on OpenStack): Postgres,
      OpenSearch, NATS JetStream, MinIO. See step 1.
- [ ] DNS for the chosen hostnames pointing at the ingress LB.
- [ ] Container images built and pushed (step 2).

## 1. Provision the backing stores

These are platform/external (forbidden as product manifests). Bring up and note their
in-cluster addresses (the overlays default to `*.evidara-platform.svc`):

- **Postgres** — create a `platform_control` database + user.
- **OpenSearch** — single node is fine to start; note URL + credentials.
- **NATS JetStream** — enable JS, then create the stream the publishers/consumer use:

  ```bash
  nats --server nats://<nats-host>:4222 stream add EVIDARA \
    --subjects 'evidara.>' --storage file --retention limits \
    --discard old --dupe-window 2m --defaults
  ```

- **MinIO** — create the raw-artifacts bucket:

  ```bash
  mc alias set hetzner http://<minio-host>:9000 <root-user> <root-pass>
  mc mb --ignore-existing hetzner/evidara-raw-artifacts-staging
  ```

> The `docker-compose.local.yml` `nats` + `minio` profiles stand up the same stream and
> bucket locally if you want to rehearse first.

## 2. Build & push images

CI (`.github/workflows/runtime-images.yml`) builds `ghcr.io/<owner>/evidara-*`. Confirm
the tags the overlays expect exist (`staging`, then `dev`/`prod`):

```bash
# e.g. trigger the image workflow, or verify tags are present in GHCR
# images: evidara-platform-control{,-admin,-worker}, evidara-legal-search-{api,frontend},
#         evidara-document-intelligence-{document-service,consumer}
```

If your registry owner differs from `philipplukas`, update `images[].name` in
`k8s/gitops/{dev,staging}/kustomization.yaml`.

## 3. Seed Vault secrets

Populate the Vault paths the `ExternalSecret`s reference (see `k8s/gitops/base/*.yaml`):

| Vault key | Properties |
| --- | --- |
| `evidara/platform-control` | `database_url` |
| `evidara/object-storage` | `access_key_id`, `secret_access_key` |
| `evidara/opensearch` | `username`, `password` |

`database_url` form: `postgresql+asyncpg://platform_control:<pw>@<pg-host>:5432/platform_control`.

## 4. Fill overlay placeholders

In `k8s/gitops/staging/kustomization.yaml` (then dev/prod) replace:

- [ ] Ingress hosts (`*.staging.evidara.example`) with real DNS names.
- [ ] `*_S3_ENDPOINT_URL`, `OPENSEARCH_NODE`, `*_NATS_SERVERS` / `NATS_SERVERS` with the
      step-1 addresses.
- [ ] `RAW_ARTIFACT_BUCKET` if different from `evidara-raw-artifacts-staging`.
- [ ] `NEXT_PUBLIC_API_URL` / `NEXT_PUBLIC_CONTROL_PANEL_URL` with the real hosts.

Validate the render before committing:

```bash
kubectl kustomize k8s/gitops/staging | less   # or: bash scripts/validate_k8s_gitops_kustomize.sh
```

## 5. Run DB migrations + seed

One-off Job (or `kubectl run`) using the platform-control image against the new Postgres.
The image exposes Alembic and the seed console script:

```bash
kubectl -n evidare-staging run pc-migrate --rm -i --restart=Never \
  --image=ghcr.io/<owner>/evidara-platform-control:staging \
  --env="PLATFORM_CONTROL_DATABASE_URL=<database_url>" \
  --command -- sh -c 'alembic upgrade head && platform-control-seed-reference-data'
```

Confirm the Alembic head matches the repo (`20260426_0017` at time of writing).

## 6. Deploy via Argo CD

Create/point an Argo `Application` at `k8s/gitops/staging` (the Application object lives in
the cluster/MacConfig repo, not here — see
`docs/migration/examples/product-argocd-application.template.yaml`). Sync and watch:

```bash
kubectl -n evidare-staging get deploy,po,ingress,externalsecret
kubectl -n evidare-staging rollout status deploy/platform-control-api
```

Each `ExternalSecret` should report `SecretSynced`; each Deployment should reach Ready.

## 7. Validate the full flow

- [ ] **Health**: `curl https://control-api.staging.<domain>/health`, same for legal-search-api.
- [ ] **Search baseline**: open the frontend host; confirm seeded results return.
- [ ] **publish → consume** (the migration's whole point): trigger a run in
      platform-control, then watch the consumer pick it up and emit `document.processed`:

  ```bash
  kubectl -n evidare-staging logs deploy/di-nats-consumer -f   # expect "message_processed"
  ```

  Confirm the new document becomes searchable in the frontend.
- [ ] **Agent/CLI smoke** (optional): point the CLI at the new hosts and run
      `EVIDARA_CLI_SMOKE=1 bash scripts/smoke-evidara-cli.sh`.
- [ ] **Broker integration test** (recommended before trusting cutover): run the
      opt-in real-NATS test — `cd document-intelligence && EVIDARA_NATS_IT=1 uv run --extra it pytest tests/test_nats_integration.py`.
- [ ] **Object-store integration test** (recommended for the same reason): run the opt-in
      MinIO test — `cd document-intelligence && EVIDARA_MINIO_IT=1 uv run --extra it --extra test pytest tests/test_delta_s3_integration.py`.
      It is the only test that reads canonical Delta over `s3://` rather than a local path, so it is
      what covers the MinIO branch of `delta_dataset_filesystem` (#825) and the credentials the
      targeted-rescore store reads with (#847). CI does not run it.

## 8. Re-point CI smokes (optional)

The five nightlies were disabled in Slice 1 (`.github/workflows/*`, schedule commented).
Once staging is healthy you can repoint them at the new hosts and re-enable the
`schedule:` triggers, or leave them on `workflow_dispatch` only.

## 9. Decommission GCP

Only after staging (and prod, when promoted) is validated:

1. `docs/runbooks/gcp-cost-stop.md` steps 2–7 — scale Cloud Run to zero, stop Cloud SQL,
   stop the OpenSearch VM (reversible).
2. Snapshot anything you still want (gcp-cost-stop step 6).
3. `docs/runbooks/gcp-cost-stop.md` step 8 — `terraform destroy` the GCP runtime stack
   (flip `deletion_protection=false` on Cloud SQL first).
4. Revoke the Workload Identity Federation bindings the old deploy workflows used.

## Promote to prod

Repeat steps 3–7 for `evidare-prod`: activate `k8s/gitops/prod/kustomization.yaml`
(uncomment `../base`, set `namespace: evidare-prod`, prod image tags, prod hosts), seed
prod Vault paths, migrate the prod DB, and point a prod Argo Application at
`k8s/gitops/prod`.

## Rollback

Until step 9 runs, GCP is intact and reversible (gcp-cost-stop is scale-to-zero, not
destroy). If the Hetzner stack misbehaves, re-scale the GCP services back up
(`gcp-cost-stop` "Rollback") and pause the Argo sync. The old Pub/Sub consumer
(`runtime_consumer.py`) is retained until cutover is confirmed, so the GCP event path
still works during the coexistence window.
