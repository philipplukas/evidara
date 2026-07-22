# Postgres backup and restore (CloudNativePG)

Owner: Platform team
Last reviewed: 2026-07-22
Last verified: 2026-07-22 — full restore drill run against the live cluster, all row
counts matched (see [Restore drill](#restore-drill-run-this-quarterly))
Applies to: prod (self-hosted Hetzner k3s, ADR-0029)

## Overview

`evidara-pg` (CloudNativePG, `instances: 1`) holds **`platform_control`** and
**`nessie`**. Per ADR-0038 §2b these are *unrecoverable by rebuild*: losing
`platform_control` loses every run, approval, source and operator row. `nessie` is the
Iceberg catalog — losing it orphans the lakehouse data in MinIO.

Backups are **base backup + continuous WAL archiving**, which gives point-in-time
recovery, not just "whatever the last snapshot had". Config lives in
[`infra/hetzner/postgres-cluster.yaml`](../../infra/hetzner/postgres-cluster.yaml).

| | |
|---|---|
| Destination | `s3://evidara-pg-backups/` on in-cluster MinIO (`http://minio.evidara.svc:9000`) |
| Base backup | Nightly 02:30 UTC — `ScheduledBackup/evidara-pg-nightly` |
| WAL archiving | Continuous |
| Retention | 30 days |
| Credentials | Secret `cnpg-minio-backup`, a MinIO user scoped to the backup bucket only |

## ⚠️ This is not yet a real backup

**MinIO's PVC is `local-path` on the same physical disk as the Postgres PVC** — both are
`/dev/md2` on the single node. So the current setup protects against:

- a bad migration, a wrong `DELETE`, table corruption, a botched deploy

and does **not** protect against:

- loss of the node, loss of the disk, or loss of the Hetzner account

**ADR-0038 step 2 requires a restore-tested path before anything depends on it. An
offsite destination is a prerequisite before Zitadel holds real user credentials** — an
IdP backed up only to the disk it runs on does not clear that bar.

Moving offsite changes three fields only (`destinationPath`, `endpointURL`,
`s3Credentials`); the mechanism proven here is unchanged.

## Health checks

Run these before trusting a backup. A silently failing archiver is the usual way people
discover at restore time that they had nothing.

```bash
# 1. CNPG's own view — want ContinuousArchiving = True
kubectl -n evidara get cluster evidara-pg \
  -o jsonpath='{range .status.conditions[*]}{.type}={.status}{"\n"}{end}'

# 2. failed_count MUST be 0
kubectl -n evidara exec evidara-pg-1 -c postgres -- \
  psql -U postgres -xtAc "SELECT archived_count, failed_count, last_archived_wal, \
                                 last_failed_wal FROM pg_stat_archiver;"

# 3. Most recent completed backup
kubectl -n evidara get backup --sort-by=.metadata.creationTimestamp
```

Take an on-demand backup (does not disturb the schedule):

```bash
kubectl -n evidara create -f - <<'EOF'
apiVersion: postgresql.cnpg.io/v1
kind: Backup
metadata:
  generateName: pg-manual-
  namespace: evidara
spec:
  cluster:
    name: evidara-pg
EOF
```

## Restore drill (run this quarterly)

**Never restore over production.** Bootstrap a *separate* cluster from the backup and
compare it against production, then delete it.

Two things that are easy to get wrong and both cause real damage:

- `serverName: evidara-pg` in `externalClusters` — this is how the new cluster knows
  *whose* backup to read. Omit it and it looks for a backup under its own name.
- **No `backup:` block on the test cluster.** If you copy it across, the restored cluster
  starts archiving into the *same* path and corrupts the source's WAL timeline.

```bash
# 1. Capture production ground truth FIRST — decide what "worked" means before restoring
kubectl -n evidara exec evidara-pg-1 -c postgres -- psql -U postgres -d platform_control -tAc "
SELECT 'jurisdictions='||(SELECT count(*) FROM jurisdictions)
UNION ALL SELECT 'authorities='||(SELECT count(*) FROM authorities)
UNION ALL SELECT 'operators='||(SELECT count(*) FROM operators)
UNION ALL SELECT 'runs='||(SELECT count(*) FROM runs)
UNION ALL SELECT 'sources='||(SELECT count(*) FROM sources)
UNION ALL SELECT 'alembic='||(SELECT version_num FROM alembic_version);"

# 2. Bootstrap a throwaway cluster from the backup
kubectl apply -f - <<'EOF'
apiVersion: postgresql.cnpg.io/v1
kind: Cluster
metadata:
  name: evidara-pg-restoretest
  namespace: evidara
spec:
  instances: 1
  storage: { size: 20Gi, storageClass: local-path }
  resources: { requests: { cpu: 100m, memory: 512Mi } }
  bootstrap:
    recovery:
      source: pg-backup-source
  externalClusters:
    - name: pg-backup-source
      barmanObjectStore:
        serverName: evidara-pg
        destinationPath: s3://evidara-pg-backups/
        endpointURL: http://minio.evidara.svc:9000
        s3Credentials:
          accessKeyId: { name: cnpg-minio-backup, key: ACCESS_KEY_ID }
          secretAccessKey: { name: cnpg-minio-backup, key: ACCESS_SECRET_KEY }
        wal: { compression: gzip }
EOF

kubectl -n evidara get cluster evidara-pg-restoretest -w   # -> Cluster in healthy state

# 3. Re-run the same query against the restored pod and diff the output
kubectl -n evidara exec evidara-pg-restoretest-1 -c postgres -- psql -U postgres \
  -d platform_control -tAc "...same query as step 1..."

# 4. ALWAYS tear down — it holds a 20Gi PVC
kubectl -n evidara delete cluster evidara-pg-restoretest
kubectl -n evidara get pvc | grep restoretest    # expect: no rows
```

A restored cluster also contains an extra empty `app` database. That is CNPG's default
bootstrap database, not corruption.

### Point-in-time recovery

To recover to a moment (e.g. just before a bad migration at 14:05), add a
`recoveryTarget` to the `bootstrap.recovery` block:

```yaml
  bootstrap:
    recovery:
      source: pg-backup-source
      recoveryTarget:
        targetTime: "2026-07-22 14:04:00+00"
```

This is why WAL archiving matters: without it you could only return to the nightly
base backup.

## Break-glass

**If the backup credential is lost or MinIO is unreachable**, backups stop but Postgres
keeps serving — `archive_command` failures accumulate WAL on the PVC. Watch disk: a
wedged archiver will eventually fill `/var/lib/postgresql/data` and *then* take the
database down. Check `failed_count` (above) and free space:

```bash
kubectl -n evidara exec evidara-pg-1 -c postgres -- df -h /var/lib/postgresql/data
```

To re-provision the scoped MinIO user, see
[`infra/hetzner/README.md`](../../infra/hetzner/README.md) Stage 1.

**If CNPG itself is broken**, the data is still a normal Postgres directory on the PVC;
`kubectl -n evidara exec evidara-pg-1 -c postgres -- pg_dumpall -U postgres` still works
and is the fastest way to get bytes out under pressure.

## Known gaps

- **Single instance.** `instances: 1` — no replica, no failover. A node loss is an outage
  regardless of backups (ADR-0038 §2b).
- **Destination is not offsite.** See the warning above. This is the blocking item.
- **CNPG 1.24.0 is past upstream EOL.** Worth an upgrade before an IdP depends on it.
- **Restore drill is manual.** Not yet wired to CI or a reminder.
