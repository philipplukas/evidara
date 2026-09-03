# ADR-0049: Workloads never hold the object-store root credential

## Status

Proposed

## Date

2026-09-03

## Context

### One credential, three buckets, six workloads

The self-hosted runtime (ADR-0029) keeps everything of value in three MinIO buckets:

| Bucket | Contents |
|---|---|
| `evidara-raw-artifacts` | captured source documents — the input to every pipeline |
| `evidara-lakehouse` | the Iceberg / Delta canonical surfaces |
| `evidara-pg-backups` | Postgres PITR backups (ADR-0038 §2) |

Until now, `platform-control-api`, `platform-control-retention-sweep`, `di-consumer`,
`document-service`, `projection-bridge` and both Trino pods all authenticated to MinIO as
**root**, and root grants all three. The mechanism was not a decision anyone made: the
credential was written into `evidara-app-secrets`, and every workload takes that Secret
with `envFrom`, so each got it whether or not it made a single S3 call. `projection-bridge`
makes none at all and held it anyway.

The consequence is the one that matters: a compromise of *any* one of those services
reached the backups that exist to recover from a compromise of those services. Recovery
and the thing recovered from shared a key.

### #792 fixed the leak and said so

`rootPassword: change-me-minio-root` sat on `main` from #504 and was the credential the
cluster was actually running. #792 rotated it, moved it into a Secret, and added
`scripts/check_hetzner_minio_credentials.py` so it could not be committed again. It
deliberately did not change who holds it — that was scoped out, and is this ADR.

### The pattern already existed, applied once

ADR-0038 §2 did not use root for Postgres backups. It provisioned a `cnpg-backup` MinIO
user with a policy naming only `evidara-pg-backups`, and — the part that makes it real —
recorded a deny check next to it:

```
cnpg-backup -> evidara-pg-backups/      OK
cnpg-backup -> evidara-raw-artifacts/   Access Denied
```

So the question is not what to do. It is why that shape was applied to one workload and
not the rest.

## Decision

**No workload authenticates to the object store as root. Each gets its own account,
scoped to the buckets and actions its code performs, and that scope is asserted by an
observed denial rather than by a policy document.**

Four commitments follow from that sentence.

1. **Root is administrative only.** It provisions the other accounts, seeds the probe
   objects the deny tests need, and answers to an operator at a console. Nothing under
   `infra/hetzner/apps/`, `infra/hetzner/values/`, `postgres-cluster.yaml` or
   `deploy-stage4.sh` may reference the `minio-root` Secret;
   `scripts/check_hetzner_minio_credentials.py` walks every one of those files for a
   `secretRef`/`secretKeyRef` naming it and fails the build.

2. **Scope is derived from code, not from convenience.** `platform-control` writes and
   deletes raw artifacts and never reads one back, so it has no `s3:GetObject`.
   `document-service` only reads the canonical surfaces, so it has no write. A grant
   nobody can point at a call site is not granted. Where the needed scope is genuinely
   unclear, the narrowest defensible policy is written and the uncertainty is recorded in
   `infra/hetzner/README.md` and in `accounts.json` — not resolved with a wildcard.

3. **A scope is not real until a denial is observed — against an object that exists.**
   `verify-minio-scoping.sh` asserts, per account per bucket, that list/read/write are
   permitted or denied exactly as declared. Root seeds a probe object first, because a
   read denied for want of the object is not a permission result: the first version of
   that script probed an absent key, so every read assertion passed unconditionally and
   the guarantee it was cited for did not exist. A test that cannot fail is worse than no
   test, because it is quoted as evidence. Probes are always placed inside the account's
   granted prefix, for the same reason.

4. **One source of truth, checked at the granularity of the claim.**
   `infra/hetzner/minio-policies/accounts.json` declares the accounts, their Secrets,
   their env-var field names, the buckets each may reach, the **operations** it may
   perform there (`ro`/`wo`/`rw`) and the **key prefix** it is confined to. The
   provisioning script, the verification script and the CI guard all read it, and the
   guard asserts each policy document's buckets, actions *and* object prefix against it.
   Bucket-set equality alone would not do: granting `s3:PutObject` on
   `evidara-lakehouse/canonical/*` to the read-only `document-service` changes no bucket
   set, and would let a compromised read API corrupt the canonical surfaces legal-search
   indexes.

This is not a claim that per-workload credentials defeat a cluster-admin. Anyone with
`kubectl get secret` in the `evidara` namespace reads all of them. What it removes is the
much likelier path: one application-level compromise reaching everything the platform
holds, including its own backups.

## Consequences

### What gets better

- A compromise is contained to the buckets one workload actually uses. In particular,
  nothing that processes untrusted fetched documents can touch `evidara-pg-backups`.
- `projection-bridge` holds no storage credential at all, because it makes no storage
  call.
- Root rotation stops being a fleet-wide event. The per-workload users are separate IAM
  records; rotating root re-encrypts them but does not change them, so no app restart is
  needed — a real improvement on the previous procedure, where every consumer held its own
  copy of root and all of them had to be restarted.

### What gets harder

- **A new S3 call path now needs a policy change.** This is the intended cost and the
  main failure mode: a widened code path with an unwidened policy fails at runtime with
  `AccessDenied`. The mitigations are that the scopes are documented against `file:line`
  in `infra/hetzner/README.md`, and that `verify-minio-scoping.sh` states the current
  boundary precisely enough to diff against.
- **Provisioning is a script against a live cluster, not `terraform apply`.** No
  Terraform manages the Hetzner cluster — `infra/terraform/` is entirely GCP and GitHub,
  which ADR-0029 moved off. Introducing a MinIO Terraform provider would mean a new
  provider, a new state backend and a second deployment mechanism for one cluster, which
  is a larger architectural change than this security fix should carry. The scripts are
  declarative in the way that matters: the desired state is committed JSON, the scripts
  reconcile to it idempotently, and a separate verifier asserts the result. Revisit if
  the Hetzner runtime ever acquires Terraform for anything else.
- **Five accounts to rotate instead of one.** `provision-minio-users.sh <user>` rotates
  one without touching the others, which the shared credential could not do at all.

### Not covered — say these out loud rather than let the ADR imply otherwise

- **Root is not rotated by this change, so every previously-issued root credential stays
  valid MinIO auth.** Workloads stop *using* it; nothing *revokes* it. Rotation is a
  scheduled follow-up (procedure in `infra/hetzner/README.md`), kept out of the cutover
  window because an IAM re-encryption failing at the same time as a credential cutover is
  unattributable. Until it happens, this change reduces the blast radius of a *future*
  compromise, not of a past one.
- **The `console` MinIO user is outside `accounts.json`.** It predates this change and is
  neither scoped nor verified here; if it carries `consoleAdmin` it is a second
  root-equivalent. The cutover runbook's Step 6 audits it and gives a decision rule.
- **`di-consumer`'s grant does not cover the Iceberg path.** It is scoped to
  `evidara-lakehouse/canonical/*`, where the Delta sink writes. The Iceberg sink of
  ADR-0036 reuses the same credential against the Nessie warehouse root
  `s3://evidara-lakehouse`, outside that prefix. Inert today (`DI_ICEBERG_CATALOG_URI` is
  unset), and deliberately left narrow rather than pre-widened for a path nothing runs —
  but whoever enables it must widen the policy in the same PR. Recorded in
  `accounts.json`'s `KNOWN GAP` note and the runbook's troubleshooting table so it
  surfaces as a documented step rather than an unexplained `AccessDenied`.
- **`k8s/gitops/`** — the Argo/MacConfig tree pulls object-storage credentials from one
  `evidara/object-storage` vault entry shared by platform-control and DI. Same defect,
  different environment and a different secret mechanism; it needs its own change.
- **Namespace RBAC.** Per-workload credentials narrow what a compromised *workload*
  reaches. Narrowing what a compromised *operator credential* reaches is separate work.
- **Local development.** `docker-compose.local.yml` runs MinIO with `minioadmin` in a
  throwaway container; there is no blast radius on a laptop.

## References

- #813 (this change), #792 (the leak), #811 (the rotation)
- [ADR-0029](0029-self-hosted-hetzner-runtime.md) — the self-hosted runtime this applies to
- [ADR-0038](0038-user-identity-and-operator-attribution.md) §2 — the `cnpg-backup` account and
  deny test this generalises
- [`infra/hetzner/README.md`](../../infra/hetzner/README.md) — the scope table and its
  `file:line` justification
- [`docs/runbooks/minio-least-privilege-cutover.md`](../runbooks/minio-least-privilege-cutover.md)
  — the cutover and rollback procedure
