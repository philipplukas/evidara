# Observability on the Hetzner cluster

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

## Alerts

`severity: critical` routes to the Alertmanager `page` receiver; `warning` to `default`.
The full list and the reasoning is in [ADR-0032](../adr/0032-pipeline-observability.md);
what to do when one fires is in
[the alert-response playbook](../runbooks/alert-response-playbook.md).

### Wiring the receivers

Two tiers, and the split is the whole point:

| Tier | Receiver | Channel | Why |
|---|---|---|---|
| `critical` | `page` | **Telegram** | A real phone push. These mean *the product is down* — read alias unresolved, index empty, every query returning nothing. The June/July outage was exactly this and went unnoticed for weeks, because nothing pushed. Repeats hourly until resolved. |
| `warning` | `default` | **Slack** | A feed you check, not a pager. Dead-letters, backlogs, probe flaps — real, but they can wait for business hours. |

Delivery is deliberately **external to this cluster**. Self-hosting the notifier here
(ntfy, Gotify) would mean a node failure silences the alerts about the node failure.

Both credentials live in one Secret, mounted into Alertmanager as *files*, so they never
enter git and never appear in `helm get values`.

**1. Create a Telegram bot** — message [@BotFather](https://t.me/botfather), send
`/newbot`, and keep the token it gives you. Then send your new bot any message and read
your chat id back:

```bash
curl -s "https://api.telegram.org/bot<TOKEN>/getUpdates" | jq '.result[0].message.chat.id'
```

**2. Create the Secret** (all three keys are required):

```bash
kubectl -n monitoring create secret generic evidara-alertmanager \
  --from-literal=slack-webhook-url='https://hooks.slack.com/services/...' \
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

The Prometheus Operator watches all namespaces (the Helm values nil the namespace-scoped
selectors), so no Helm change is needed.

## Cost

On the single dedicated node, at 15d retention: Prometheus ~1–3 GiB RAM + 20 GiB disk,
Grafana ~128–512 MiB + 2 GiB, Alertmanager ~128–256 MiB + 2 GiB, plus node-exporter and
kube-state-metrics. Fixed, not usage-billed — consistent with ADR-0029.
