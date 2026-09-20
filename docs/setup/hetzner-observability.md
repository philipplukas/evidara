# Observability on the Hetzner cluster

> **Platform commands here have moved.** `deploy-stage{1,2,3,8}.sh`,
> `deploy-observability.sh`, `deploy-runners.sh` and the `values/` files now live in
> [research-platform](https://github.com/philipplukas/research-platform) (`scripts/`, `data/`,
> `identity/`, `observability/`). The copies under `infra/hetzner/` are frozen duplicates
> awaiting deletion — see [`infra/hetzner/OWNERSHIP.md`](../../infra/hetzner/OWNERSHIP.md).
> Stages 4 and 5 are still run from this repository.

Prometheus + Alertmanager + Grafana on the self-hosted k3s cluster, and the pipeline
funnel dashboard that makes a broken pipeline visible in five seconds instead of a
session with `kubectl`. See [ADR-0032](../adr/0032-pipeline-observability.md) for why,
and [ADR-0029](../adr/0029-self-hosted-hetzner-runtime.md) for the cluster itself.

> **The problem this solves.** Liveness probes answer *"is the process alive"*. During
> the June/July outage every pod was `Running`, `1/1 Ready`, zero restarts, clean logs —
> while search returned an empty page for every query, for weeks. Nothing answered
> *"is work actually flowing"*.

## Deploy

```bash
export KUBECONFIG=~/.kube/evidara-hetzner.yaml
bash infra/hetzner/deploy-observability.sh
```

Idempotent. It installs `kube-prometheus-stack` into a new `monitoring` namespace,
re-applies the NATS release (to add the JetStream exporter sidecar), and applies the
Evidara scrape targets, alert rules, and funnel dashboard.

The Grafana admin password is generated **once** into the `evidara-grafana-admin` Secret
and preserved on re-runs — the same create-once pattern as `evidara-auth` in stage 5.

| File | What it is |
|---|---|
| `infra/hetzner/values/kube-prometheus-stack.yaml` | Helm values (retention, storage, k3s adjustments, Grafana sidecar) |
| `infra/hetzner/observability/scrape-targets.yaml` | `ServiceMonitor` / `PodMonitor` per service |
| `infra/hetzner/observability/alerts.yaml` | `PrometheusRule` — the day-one alerts |
| `infra/hetzner/observability/dashboard-funnel.yaml` | The funnel dashboard, as a labelled ConfigMap |
| `infra/hetzner/observability/dashboard-run-logs.yaml` | The run-scoped log dashboard (see [Logs](#logs)) |

## Reach the UIs

There is no Ingress for these — they are operator tools, reached over `port-forward`.

```bash
kubectl -n monitoring port-forward svc/kps-grafana 3000:80        # http://localhost:3000
kubectl -n monitoring get secret evidara-grafana-admin \
  -o jsonpath='{.data.admin-password}' | base64 -d; echo          # user: admin

kubectl -n monitoring port-forward svc/kps-prometheus 9090:9090
kubectl -n monitoring port-forward svc/kps-alertmanager 9093:9093
```

Grafana → **Dashboards → Evidara → "Evidara — pipeline funnel"**.

## The funnel

One number per stage, over the dashboard's time range. Read it top-left to bottom-right.

| # | Stage | Metric |
|---|---|---|
| 1 | Runs launched | `platform_control_runs_launched_total` |
| 2 | Artifacts captured | `platform_control_artifacts_captured_total` |
| 3 | Bundle events published | `platform_control_bundle_events_published_total` |
| 4 | DI messages processed | `di_messages_total{outcome="processed"}` |
| 5 | `document.processed` forwarded | `di_projection_forwards_total{outcome="forwarded"}` |
| 6 | Documents indexed | `legal_search_documents_indexed_total` |
| — | Docs searchable **now** | `legal_search_indexed_documents` (gauge, not a rate) |
| 7 | Search queries | `legal_search_search_queries_total` |
| — | …with hits | queries − `legal_search_search_queries_zero_hits_total` |
| — | `documents-read` resolves | `legal_search_alias_resolved{alias="documents-read"}` (0 = search is dead) |

**A leak between two adjacent stages is a step change.** 12 runs launched, 12 messages
processed, 5 documents indexed means the projection path is dropping 7. 340 queries and
0 with hits means the index is gone. Both are one glance.

The `legal_search_search_errors_total` line on the search panel is what separates *"the
corpus genuinely has no match"* from *"OpenSearch is dead and the adapter is serving you
an empty page"* — the API degrades a failed search into an empty result set, so without
this counter those two are byte-identical.

## Logs

The funnel tells you **where** a run stopped. It never tells you **why**: that is in a
pod's stdout, which until Loki exists is reachable only by `kubectl logs` against a pod
that may already have been replaced. Twice on 2026-09-17 the line that diagnosed a
failure was destroyed by a container restart before anyone read it —
[ADR-0059](../adr/0059-an-event-is-a-fact-a-log-is-an-explanation.md) is that decision,
and #892 is the ticket.

**The stack is not deployed from this repository.** Loki and the Alloy collector live in
[research-platform](https://github.com/philipplukas/research-platform) —
`observability/loki/values.yaml`, `observability/alloy/values.yaml`, and the Grafana
datasource ConfigMap beside them — and its `scripts/deploy-observability.sh` installs
them into `monitoring` at the end of the same run that installs kube-prometheus-stack.
An edit under `infra/hetzner/values/` does not reach the cluster; see
[`infra/hetzner/OWNERSHIP.md`](../../infra/hetzner/OWNERSHIP.md).

What this repository owns is the Evidara half, applied the same way as the funnel
dashboard and in this order:

```bash
# 1. In the research-platform checkout: Loki, the datasource, Alloy.
bash scripts/deploy-observability.sh

# 2. Back here: scrape targets, alerts, both dashboards.
kubectl apply -k infra/hetzner/observability
```

Applying step 2 first is not harmful — the run-logs panels render "datasource not found"
until Loki exists, which is a visible failure rather than a quiet empty one.

### Getting from a run to that run's logs

Grafana → **Dashboards → Evidara → "Evidara — logs for one run"**, or the URL directly,
which is the form the admin panel's run detail can link to once a Grafana base URL is
configured:

```
/d/evidara-run-logs/evidara-run-logs?var-run=run_01jq7a3s9b7j4dndd9sgv6pb9d
```

The query patterns, the per-service coverage table, and the `| json` trap that turns a
parser error into a convincing "this run logged nothing" are in
[the event-tracing runbook](../runbooks/event-tracing-queries.md).

### Retention, and the measurements behind it

Upstream sets 14 days on a 20 GiB node-local PVC. Measured on this cluster on
2026-09-19:

| Measurement | Value | How |
|---|---|---|
| Container stdout, all namespaces that matter | **48 MiB/day** uncompressed | summed `kubectl logs --since=6h` over every Running pod in `evidara`, `monitoring`, `argocd`, `arc-systems` |
| Loudest single pod | `zitadel`, 4.4 MiB/6h — 35% of the total | same |
| 14 days at that rate | **0.66 GiB** uncompressed, less once chunks are compressed | — |
| Free space on `/` (control-plane node, `/dev/md2`) | 664 GiB of 872 GiB | `node_filesystem_avail_bytes{mountpoint="/"}` |
| Prometheus, for comparison | 7.5 GiB on disk at 15d / 18GB retention | `prometheus_tsdb_storage_blocks_bytes` |

So 20 GiB is roughly thirty times the steady-state need, and the node has room for it.
That headroom is the point rather than waste: the window this matters in is a crash loop
or a large acquisition run, which are orders of magnitude louder than the quiet six hours
measured above. **The caveat is real** — that window contained no acquisition run and no
CI job, so treat 48 MiB/day as a floor, not a forecast.

`local-path` is the only StorageClass on this cluster, so the PVC is pinned to the node
that first bound it and dies with that node. It survives a pod restart, which is the
failure that prompted it. It is a diagnostic store and must not be described as durable;
MinIO is already running and is the upgrade path (`storage.type: s3`) when that stops
being acceptable.

### Verify after deploying it

```bash
kubectl -n monitoring get pods -l app.kubernetes.io/name=loki
kubectl -n monitoring get ds alloy
```

`get ds alloy` reports `DESIRED` — check the number. The GPU node carries
`gpu=true:NoSchedule` and the upstream Alloy values set no toleration for it, so the
DaemonSet lands on the control-plane node only. Every Evidara workload runs there today,
so no Evidara log is lost; anything scheduled onto the GPU node is not collected. Raised
upstream as research-platform#4, together with the datasource `uid` and the verification
query below.

Then confirm a query actually parses, which is the step worth not skipping:

```bash
kubectl -n monitoring port-forward svc/kps-grafana 3000:80 &
# Explore → Loki →
#   {namespace="evidara"} | pattern "<_> <_> <_> <msg>" | line_format "{{.msg}}" | json
```

A result whose stream labels include `__error__: JSONParserErr` means the parse failed,
not that the field is absent — and a field filter appended to a failed parse returns zero
lines, which is indistinguishable from "nothing happened". The runbook has the detail.

## Alerts

`severity: critical` routes to the Alertmanager `page` receiver; `warning` to `default`.
The full list and the reasoning is in [ADR-0032](../adr/0032-pipeline-observability.md);
what to do when one fires is in
[the alert-response playbook](../runbooks/alert-response-playbook.md).

### Wiring the receivers

Two tiers, one channel — both go to the same Telegram chat:

| Tier | Receiver | Behaviour | Why |
|---|---|---|---|
| `critical` | `page` | 🔴 prefix, repeats **hourly** | *The product is down* — read alias unresolved, index empty, every query returning nothing. The June/July outage was exactly this and went unnoticed for weeks, because nothing pushed. It is meant to nag. |
| `warning` | `default` | ⚠️ prefix, repeats every **4h** | Dead-letters, backlogs, probe flaps. Real, but they can wait for business hours. |

A second channel for warnings (Slack) was considered and dropped. This is a one-operator
system, and **a channel you check "sometimes" is where alerts go to die** — which is the
failure this whole stack exists to prevent. What actually changes behaviour is the repeat
interval and the prefix, not which app the message lands in.

Delivery is deliberately **external to this cluster**. Self-hosting the notifier here
(ntfy, Gotify) would mean a node failure silences the alerts about the node failure.

The bot token is mounted into Alertmanager as a *file*, so it never enters git and never
appears in `helm get values`.

**1. Create a Telegram bot** — message [@BotFather](https://t.me/botfather), send
`/newbot`, and keep the token it gives you. Then send your new bot any message and read
your chat id back:

```bash
curl -s "https://api.telegram.org/bot<TOKEN>/getUpdates" | jq '.result[0].message.chat.id'
```

**2. Create the Secret** (all three keys are required):

```bash
kubectl -n monitoring create secret generic evidara-alertmanager \
  --from-literal=telegram-bot-token='123456:ABC-DEF...' \
  --from-literal=telegram-chat-id='123456789'
```

**3. Re-run the deploy script.** It reads `telegram-chat-id` back out of the Secret and
substitutes it at render time — Alertmanager will not read `chat_id` from a file (it must
be an inline int64), so this is the one value that has to be rendered rather than mounted.
It is inert without the bot token.

```bash
bash infra/hetzner/deploy-observability.sh
```

If the Secret is absent the script **does not fail** — the dashboards and the rules engine
still come up — but it prints a loud warning, because alerts that fire into a UI nobody
watches are indistinguishable from no alerts at all.

**4. Prove it actually delivers.** Do not skip this. An untested receiver is exactly the
class of thing this stack exists to catch:

```bash
kubectl -n monitoring port-forward svc/kps-alertmanager 9093:9093 &
curl -s -XPOST http://localhost:9093/api/v2/alerts -H 'Content-Type: application/json' -d '[{
  "labels": {"alertname": "ReceiverSmokeTest", "severity": "critical"},
  "annotations": {"summary": "If you can read this on your phone, the page tier works."}
}]'
```

Your phone should buzz within ~30s (`group_wait`). Repeat with
`"severity": "warning"` to prove the Slack tier.

## Verify after the first rollout

```bash
# 1. Every target is UP. A target that is DOWN has taken all of its own alerts with it.
kubectl -n monitoring port-forward svc/kps-prometheus 9090:9090 &
curl -s 'http://localhost:9090/api/v1/targets?state=active' \
  | jq -r '.data.activeTargets[] | select(.labels.namespace=="evidara") | "\(.health)\t\(.labels.job)"'

# 2. The funnel metrics exist.
for m in platform_control_runs_launched_total di_messages_total \
         legal_search_search_queries_total legal_search_alias_resolved; do
  printf '%s -> ' "$m"
  curl -s "http://localhost:9090/api/v1/query?query=$m" | jq -r '.data.result | length'
done

# 3. The JetStream metric names resolve. The prometheus-nats-exporter `jsz` collector
#    names these, and the name has moved between exporter versions — an alert on a
#    metric that does not exist is worse than no alert, because it looks like one.
curl -s 'http://localhost:9090/api/v1/query?query=nats_consumer_num_pending' \
  | jq -r '.data.result | length'    # expect >= 1, NOT 0
```

If (3) returns `0`, list what the exporter actually publishes and fix the two JetStream
rules in `infra/hetzner/observability/alerts.yaml`:

```bash
curl -s 'http://localhost:9090/api/v1/label/__name__/values' | jq -r '.data[] | select(startswith("jetstream"))'
```

## Editing the dashboard

The Grafana sidecar imports any ConfigMap labelled `grafana_dashboard: "1"`. Edit
`infra/hetzner/observability/dashboard-funnel.yaml` and re-apply — no Helm upgrade, no
Grafana restart:

```bash
kubectl apply -k infra/hetzner/observability
```

Changes made in the Grafana UI are **not** persisted back to the repo. Export the JSON
from the UI and paste it into the ConfigMap, or the next apply overwrites them.

## Adding a service

1. Expose `/metrics` on the service (see `document_intelligence/observability/metrics.py`
   or `legal-search/api/src/core/metrics/` for the two patterns).
2. Give the Service (or the pod's `containerPort`) a **named** port — `ServiceMonitor`
   and `PodMonitor` target ports by name.
3. Add a block to `infra/hetzner/observability/scrape-targets.yaml`.
4. `kubectl apply -k infra/hetzner/observability`.
5. If the service emits structured logs via an `observability/event_logging.py`, make sure
   it can name its environment — `PLATFORM_CONTROL_ENVIRONMENT` for platform-control,
   `DI_ENVIRONMENT` for document-intelligence, both set in
   `infra/hetzner/apps/configmap.yaml`. Every log line carries an `environment` field, and
   for as long as it read an unprefixed `ENVIRONMENT` that nothing set, every production
   line read `environment="unknown"` (#712). See
   [environment-strategy.md](environment-strategy.md#which-variable-names-an-environment).
   A tag that is silently wrong is the same failure mode as this page's opening warning:
   the signal looks healthy precisely because nothing errored.

The Prometheus Operator watches all namespaces (the Helm values nil the namespace-scoped
selectors), so no Helm change is needed.

## Cost

On the single dedicated node, at 15d retention: Prometheus ~1–3 GiB RAM + 20 GiB disk,
Grafana ~128–512 MiB + 2 GiB, Alertmanager ~128–256 MiB + 2 GiB, plus node-exporter and
kube-state-metrics. With logs: Loki ~256 MiB–1 GiB + 20 GiB disk at 14d, and Alloy
~128–512 MiB per node. Fixed, not usage-billed — consistent with ADR-0029.
