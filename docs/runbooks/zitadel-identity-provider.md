# Zitadel (identity provider) — operations, restore, break-glass

Owner: Platform team
Last reviewed: 2026-07-23
Last verified: **never — see [Status](#status-not-yet-verified-against-a-live-cluster)**
Applies to: prod (self-hosted Hetzner k3s, ADR-0029)

> **Platform commands here have moved.** `deploy-stage{1,2,3,8}.sh`,
> `deploy-observability.sh`, `deploy-runners.sh` and the `values/` files now live in
> [research-platform](https://github.com/philipplukas/research-platform) (`scripts/`, `data/`,
> `identity/`, `observability/`). The copies under `infra/hetzner/` are frozen duplicates
> awaiting deletion — see [`infra/hetzner/OWNERSHIP.md`](../../infra/hetzner/OWNERSHIP.md).
> Stages 4 and 5 are still run from this repository.

## Status: not yet verified against a live cluster

Everything below was written against the chart and the cluster manifests, not against
a running Zitadel. The chart renders (`scripts/check_hetzner_zitadel.py --render`) and
the SQL, secrets and ingress follow patterns already proven on this cluster — but no
part of this document has been executed. Treat every command as a proposal until the
[deployment checklist](#deployment-checklist) has been walked once and this header is
updated with a date.

**ADR-0038 §8 step 2 is not complete until [the restore drill](#restore-drill-the-gate)
has passed.** Nothing in §8 steps 3-7 may start before then. That is the ADR's own
sequencing rule and it is the reason this file exists.

## What this is

Zitadel is the self-hosted OIDC provider chosen in [ADR-0038 §2](../adr/0038-user-identity-and-operator-attribution.md).
As of this document it is **deployed and load-bearing for nothing**: no application
authenticates against it, and both UIs are still behind the single shared Traefik
BasicAuth password. Wiring it up is ADR-0038 §8 steps 4-7.

| | |
|---|---|
| Chart | `zitadel/zitadel` **10.0.4** (app `v4.15.3`), pinned in `deploy-stage8.sh` |
| Values | [`infra/hetzner/values/zitadel.yaml`](../../infra/hetzner/values/zitadel.yaml) |
| Deploy | [`infra/hetzner/deploy-stage8.sh`](../../infra/hetzner/deploy-stage8.sh) (idempotent) |
| Public URL | `https://id.evidara.veyo.dev` — Traefik + cert-manager `letsencrypt-prod` |
| Database | `zitadel` in the existing CNPG cluster `evidara-pg`, own role `zitadel` |
| Secrets | `zitadel-db` (DSN), `zitadel-masterkey` (32-byte encryption key) |
| Backups | inherited from [`postgres-backup-and-restore.md`](postgres-backup-and-restore.md) — nothing per-database was added |

### Two things that are not obvious

1. **The masterkey is not in the database backup.** Zitadel encrypts private keys and
   tokens with `zitadel-masterkey` before storing them. A perfect Postgres restore
   without that key gives you an instance that cannot decrypt its own data. It is a
   *separate* backup artifact with a *separate* handling rule (below).
2. **Nothing per-database was added to the backup config.** `barmanObjectStore` on
   `evidara-pg` archives the whole instance's WAL stream, so `zitadel` was covered the
   moment the database existed. The work in ADR-0038 §8 step 2 is therefore not
   "configure a backup" — it is "prove the restore", which is the drill below.

## Deployment checklist

Ordered. Each step is verifiable before the next.

1. **DNS.** `id.evidara.veyo.dev` → `88.99.26.120` (A record; IPv4 only — the node does
   not serve 443 over IPv6, same as `admin.` and `search.`). Confirm it resolves before
   applying anything, or cert-manager's HTTP-01 challenge fails.
2. **First apply on the staging issuer.** Change both
   `cert-manager.io/cluster-issuer` values in `values/zitadel.yaml` to
   `letsencrypt-staging`, run the deploy, confirm a cert is issued (it will be an
   untrusted "STAGING" one), then flip back to `letsencrypt-prod` and re-run. This is
   the same rate-limit dodge the README documents for the other two hosts.
3. **Deploy.** `bash infra/hetzner/deploy-stage8.sh`
4. **Verify the issuer URL**, which is the value everything downstream will be
   configured against:

   ```bash
   curl -sS https://id.evidara.veyo.dev/.well-known/openid-configuration | jq -r .issuer
   # MUST be exactly: https://id.evidara.veyo.dev
   ```

   If it comes back with a port, `http://`, or a different host, `ExternalDomain` /
   `ExternalPort` / `ExternalSecure` disagree with the ingress. Fix that before going
   further; every redirect URI in ADR-0038 §8 steps 5-7 is derived from it.
5. **Capture the initial credentials** (below) and store them out-of-band.
6. **Back up the masterkey** out-of-band. Do not skip and come back to it.
7. **Run [the restore drill](#restore-drill-the-gate).** Only then is step 2 done.

### Initial credentials

The chart's setup job seeds an IAM admin. Extract and store, then verify you can log
in to `https://id.evidara.veyo.dev/ui/console`:

```bash
# Machine (service account) key — JSON, for the management API
kubectl -n evidara get secret iam-admin -o jsonpath='{.data.iam-admin\.json}' | base64 -d

# Personal access token for the same machine user
kubectl -n evidara get secret iam-admin-pat -o jsonpath='{.data.pat}' | base64 -d

# The human admin (zitadel-admin@zitadel.id.evidara.veyo.dev) gets a generated
# password printed by the setup job. Read it BEFORE the job log is rotated away:
kubectl -n evidara logs job/zitadel-setup | grep -i -A2 password
```

> Unverified: the exact log line for the human admin password is from Zitadel's
> documented behaviour when `FirstInstance.Org.Human.Password` is unset, not from a
> run on this cluster. If it is not in the log, set a password explicitly via the
> console using the `iam-admin` machine key, and record how it actually worked here.

### Back up the masterkey (do this once, immediately)

```bash
kubectl -n evidara get secret zitadel-masterkey -o jsonpath='{.data.masterkey}' | base64 -d
```

Store it wherever the BasicAuth and MinIO root credentials already live — **not in this
repo**, and not only in the cluster it protects. #792 is the standing reminder of what
happens when a credential ends up on `main`.

## Health checks

```bash
kubectl -n evidara get pods -l app.kubernetes.io/instance=zitadel
kubectl -n evidara get ingress zitadel zitadel-login
kubectl -n evidara get certificate id-evidara-tls          # READY=True
curl -sS -o /dev/null -w '%{http_code}\n' https://id.evidara.veyo.dev/debug/healthz
```

Two failure modes that look like something else:

- **Login 404s while the console loads.** The login UI is a *separate* deployment
  served under `/ui/v2/login` by the `zitadel-login` Ingress. If only the `/` Ingress
  exists, the host answers and login is unreachable.
- **Certificate stuck not-ready.** cert-manager names the Certificate after the TLS
  `secretName`. Both Ingresses share `id-evidara-tls`, so exactly one of them carries
  the issuer annotation. If someone adds the annotation to the other, two Ingresses
  contend for one Certificate object. `scripts/check_hetzner_zitadel.py` fails on this.

## Restore drill (the gate)

**This is the ADR-0038 §8 step 2 acceptance criterion.** Run it once before anything
depends on Zitadel, then quarterly alongside the
[platform_control drill](postgres-backup-and-restore.md#restore-drill-run-this-quarterly).

The mechanism is identical to that drill — same cluster, same barman path — so this
adds only the `zitadel`-specific ground truth and the masterkey half that a Postgres
drill cannot cover. Read the two warnings there first (`serverName`, and **no `backup:`
block on the test cluster**); both apply unchanged.

```bash
# 1. Ground truth from production, BEFORE restoring. Decide what "worked" means first.
kubectl -n evidara exec evidara-pg-1 -c postgres -- psql -U postgres -d zitadel -tAc "
SELECT 'schemas='||(SELECT count(*) FROM information_schema.schemata
                     WHERE schema_name IN ('eventstore','projections','system','auth'))
UNION ALL SELECT 'events='||(SELECT count(*) FROM eventstore.events2)
UNION ALL SELECT 'orgs='||(SELECT count(*) FROM projections.orgs1)
UNION ALL SELECT 'users='||(SELECT count(*) FROM projections.users14);"
```

> Unverified: the projection table names carry a schema-version suffix that changes
> between Zitadel releases (`users14`, `orgs1`, …). Run
> `\dt projections.*` on the live database first and use the names you actually find —
> do not copy these forward without looking.

```bash
# 2. Bootstrap a throwaway cluster from the backup (identical to the platform_control
#    drill — the manifest is in postgres-backup-and-restore.md; it restores the whole
#    instance, so `zitadel` comes with it).
# 3. Re-run the same query against evidara-pg-restoretest-1 and diff the output.
# 4. ALWAYS tear the test cluster down; it holds a 20Gi PVC.
kubectl -n evidara delete cluster evidara-pg-restoretest
```

### The half a Postgres restore does not prove

Matching row counts prove the *data* survived. They do not prove the instance is
**usable**, because every secret in those rows is encrypted with the masterkey. To
prove that end of it, in the same drill:

```bash
# Point a throwaway Zitadel at the restored database with the SAME masterkey and
# confirm it starts and serves discovery. Never point it at the production database.
helm upgrade --install zitadel-restoretest zitadel/zitadel --version 10.0.4 -n evidara \
  -f infra/hetzner/values/zitadel.yaml \
  --set zitadel.configmapConfig.ExternalDomain=restoretest.invalid \
  --set ingress.enabled=false --set login.ingress.enabled=false \
  --set envVarsSecret=zitadel-db-restoretest \
  --wait --timeout 10m
# (create zitadel-db-restoretest first, pointing at evidara-pg-restoretest-rw)

kubectl -n evidara port-forward svc/zitadel-restoretest 8080:8080 &
curl -sS localhost:8080/debug/healthz          # 200 == the masterkey decrypts the data
helm -n evidara uninstall zitadel-restoretest  # ALWAYS
```

**Record the result** — date, row counts, whether the restored instance started — in
the header of this file. An unrecorded drill is indistinguishable from one that never
ran, which is the failure mode `Last verified:` exists to prevent.

### Known gaps, inherited and new

- **The destination is still not offsite.** MinIO's PVC is `local-path` on the same
  `/dev/md2` as the Postgres PVC. ADR-0038 §2b and the backup runbook both name this
  as **the blocking prerequisite before Zitadel holds real user credentials** — a
  disk loss takes the IdP and its backup together. Moving offsite changes three fields
  (`destinationPath`, `endpointURL`, `s3Credentials`).
- **`instances: 1`.** No replica, no failover. A node loss is a login outage, and
  after §8 step 5 that is an outage of both UIs.
- **The drill is manual.** Not wired to CI or to a reminder.

## Break-glass

ADR-0038 §2b: *"Keep a break-glass path documented in the runbook before the first
upgrade."* Four situations, worst first.

### 1. Zitadel is down and login is the only way in

**Today this is a non-event** — nothing authenticates against Zitadel yet, so a
Zitadel outage affects nothing but Zitadel. Existing Auth.js sessions will outlive a
restart once §8 step 5 lands; new logins will not.

The API-key path (`X-API-Key`, ADR-0020) is independent of Zitadel and is what keeps
the control plane reachable while the IdP is down. **Do not remove it** as part of
§8 steps 4-7: it is the break-glass, and ADR-0038 §4.1 already says it stays.

```bash
kubectl -n evidara rollout restart deploy/zitadel
kubectl -n evidara logs deploy/zitadel --tail=100
kubectl -n evidara get pods -l app.kubernetes.io/instance=zitadel
```

### 2. A bad upgrade locked everyone out

Helm keeps the previous release. Roll back before debugging:

```bash
helm -n evidara history zitadel
helm -n evidara rollback zitadel <previous-revision> --wait --timeout 10m
```

**A rollback does not undo database migrations.** Zitadel's setup job migrates the
schema forward on upgrade; if the new schema is incompatible, the rollback leaves the
old binary against a migrated database. In that case restore the `zitadel` database
to a point-in-time just before the upgrade
([PITR](postgres-backup-and-restore.md#point-in-time-recovery)) and roll the chart
back together with it. **Take a manual backup immediately before every Zitadel
upgrade** so that point exists:

```bash
kubectl -n evidara create -f - <<'EOF'
apiVersion: postgresql.cnpg.io/v1
kind: Backup
metadata: { generateName: pg-pre-zitadel-upgrade-, namespace: evidara }
spec: { cluster: { name: evidara-pg } }
EOF
```

### 3. The admin account is lost

Use the `iam-admin` machine user's key or PAT against the management API — it holds
`IAM_OWNER` and does not depend on anyone's password or MFA device:

```bash
PAT=$(kubectl -n evidara get secret iam-admin-pat -o jsonpath='{.data.pat}' | base64 -d)
curl -sS -H "Authorization: Bearer ${PAT}" https://id.evidara.veyo.dev/auth/v1/users/me
```

If that secret is also gone, the last resort is direct database access
(`kubectl -n evidara exec evidara-pg-1 -c postgres -- psql -U postgres -d zitadel`).
Zitadel is event-sourced; hand-editing `eventstore.events2` is **not** a supported
repair and will corrupt projections. Prefer a restore, or a fresh instance if the
data is not yet worth keeping — which, before §8 step 5, it is not.

### 4. The masterkey is lost

There is no recovery. Encrypted material — private keys, tokens, secrets of every
configured application — is unrecoverable, and the only path forward is a fresh
instance and re-onboarding every user. This is why it is backed up separately, on the
day it is created, and why it is not rotated casually. Say so out loud rather than
discovering it during an incident.

## Related

- [ADR-0038 — user identity, roles, and operator attribution](../adr/0038-user-identity-and-operator-attribution.md) (§2, §2b, §8 step 2)
- [Postgres backup and restore](postgres-backup-and-restore.md) — the path this joins
- [`infra/hetzner/README.md`](../../infra/hetzner/README.md) Stage 8
