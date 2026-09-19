---
name: measure-before-you-theorise
description: The read-only queries that answer "what is actually true in production" for Evidara — corpus size and coverage, why a run's documents never became searchable, what a service actually logged, DLQ depth, pod restarts and OOM kills, template lock state, and whether a deploy really rolled. Use when diagnosing a stuck run, a missing or wrong document, a failed acceptance gate, a template that will not launch, or before proposing any fix or architecture change based on how the code reads. Also lists the traps that produce confident wrong answers.
---

# Measure before you theorise

Every query here is read-only and answers a question that is otherwise guessed at.

This file exists because on 2026-09-17/18 the same defect was diagnosed wrongly
three times in a row — an OOM, then a silent 404, then the wrong source file —
and each correction came from a measurement that was available the whole time. A
three-part architecture was designed around a condition `nats stream subjects`
refuted in one command.

**The rule this encodes: when the code and the system disagree, the system is
right. Query it before you write anything, including an ADR.**

## Setup

Most queries need one of two API keys. Never pass them on a command line — argv
is world-readable (`ps`, `/proc`), which is how an operator key leaked.

```bash
export EVIDARA_PLATFORM_CONTROL_URL=https://platform-control-api.ts.veyo.dev
export EVIDARA_LEGAL_SEARCH_URL=https://legal-search-api.ts.veyo.dev
export EVIDARA_PLATFORM_CONTROL_API_KEY="$(kubectl -n evidara get secret evidara-auth \
  -o jsonpath='{.data.PLATFORM_CONTROL_OPERATOR_API_KEY}' | base64 -d)"
export EVIDARA_LEGAL_SEARCH_API_KEY="$(kubectl -n evidara get secret evidara-auth \
  -o jsonpath='{.data.LEGAL_SEARCH_API_KEY}' | base64 -d)"
```

Public surfaces need no key: search is `search.evidara.veyo.dev`; `evidara.veyo.dev`
is **marketing** and answers 401 by design. Confusing the two reads as an outage.

## What is in the corpus

```bash
curl -sS "$EVIDARA_LEGAL_SEARCH_URL/v1/coverage" -H "X-API-Key: $EVIDARA_LEGAL_SEARCH_API_KEY"
```

Totals and per-jurisdiction counts. This is the denominator for every coverage
claim. `documents_without_group_key` is not zero and is not noise.

## Why a run's documents never became searchable

```bash
curl -sS "$EVIDARA_PLATFORM_CONTROL_URL/v1/runs/$RUN/processing-status?limit=3000" \
  -H "X-API-Key: $EVIDARA_PLATFORM_CONTROL_API_KEY" | python3 -c '
import json,sys,collections
rows=json.load(sys.stdin)["data"]
by=collections.defaultdict(set)
for r in rows: by[r["document_id"]].add(r["status"])
TERMINAL={"canonical_ready","failed","quarantined","withdrawn","skipped_duplicate"}
print("documents:", len(by))
print("no terminal status:", sum(1 for v in by.values() if not (v & TERMINAL)))
print(collections.Counter(tuple(sorted(v)) for v in by.values()).most_common(5))'
```

Count **every** terminal status, not just `canonical_ready` — a quarantined
document is finished, and calling it stuck sends you hunting a failure that did
not happen.

## What a service actually logged — the trap that cost three wrong turns

**Grep the source for the log event name first, then grep the logs for that
name.** Do not invent the string from the prose in the code.

```bash
grep -rn "logger.warn\|logger.error\|log_event" <the class that is actually wired> | head
kubectl -n evidara logs deploy/<svc> --since=40m | grep -oE "<those exact names>" | sort | uniq -c
```

Two ways this goes wrong, both observed:

- Searching for `"lean fetch"` found nothing and "proved" a failure was silent.
  That string belonged to `modules/documents/document-intelligence.fetch-client.ts`,
  which was **not wired** — and which #984 deleted, because reading it cost two
  agents a diagnosis each. The wired class is `HttpDocumentIntelligenceClient`
  (`lib/document-intelligence/document-intelligence.client.ts`) and it logs
  `document_intelligence_lean_http_error`, `document_intelligence_lean_failed`
  and `document_intelligence_lean_unexpected_status`. It had logged both
  failures twice.
- **Check which implementation is injected before reading one.** Two classes can
  share a concept and only one is in the path:
  `grep -rn "useClass\|provide:" <module>.module.ts`

Logs do not survive a restart and are not aggregated yet (#892). `kubectl logs
--previous` on a crash loop returns the last container only — three startup lines
after an OOM. Absence of a log line is **not** evidence the event did not happen.

## Dead letters

```bash
kubectl -n evidara exec deploy/nats-box -- \
  nats --server nats://nats:4222 stream subjects EVIDARA
```

A non-zero `.dlq` subject means events were abandoned. This one command refuted
an entire architecture proposal. Note **which** subject: an
`artifact-bundle-available.dlq` is document-intelligence giving up, a
`document-processed.dlq` is the projection bridge — different failures with
different fixes.

Then check the documents actually overlap what you are investigating before
concluding they explain it. They did not, once.

```bash
# Consumers: 0 pending + 0 ack-pending means nothing is queued or in flight,
# so anything unfinished is abandoned rather than slow.
kubectl -n evidara exec deploy/nats-box -- \
  nats --server nats://nats:4222 consumer ls EVIDARA
```

Replay with `scripts/replay-nats-dlq.sh --dry-run` first; it never drains the queue.

## Pods, restarts and OOM

```bash
kubectl -n evidara get pod -l app=<svc> \
  -o jsonpath='{.items[0].status.containerStatuses[0].lastState}'
kubectl -n evidara top pod -l app=<svc>
```

`reason: OOMKilled`, `exitCode: 137`. A container that idles far below its limit
can still die under a batch: di-consumer sat at 76Mi and was killed seven times
in eighteen minutes against 1Gi.

## Template lock state — why a template will not run

```bash
curl -sS "$EVIDARA_PLATFORM_CONTROL_URL/v1/sources/blueprint-templates?limit=200" \
  -H "X-API-Key: $EVIDARA_PLATFORM_CONTROL_API_KEY" | python3 -c '
import json,sys
rows=json.load(sys.stdin)["data"]
print("launchable:", sum(1 for r in rows if r["launchable"]), "of", len(rows))
for r in rows:
    if not r["launchable"]:
        print(" ", r["overlay_id"]+"/"+r["provider_template_id"], r["acquisition_readiness"])'
```

`readiness=live` and not launchable means the **config key**, not the code — an
acceptance run and `workflow coverage enable` away. `scaffold`/`awaiting_evidence`
means engineering. See the `coverage-acceptance-loop` skill for the loop itself.

A template can also be blocked by **reference data**: `POST /v1/sources` answering
*"Authority does not belong to the requested jurisdiction"* means the jurisdiction
has no authority in `seeds/reference/`, not that anything is broken.

## Did the deploy actually roll

```bash
kubectl -n argocd get application evidara-apps \
  -o jsonpath='{.status.sync.status} {.status.health.status} {.status.sync.revision}'
kubectl -n evidara get deploy -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.template.spec.containers[0].image}{"\n"}{end}'
```

**The image tag is the commit the pin points AT, not the pin-roll commit.** A
waiter grepping deployments for the pin-roll SHA waits forever. Argo can also
report `Synced` at a revision *older* than your merge because it has not polled
yet — compare timestamps before concluding anything.

Reference seeds ship **in the image** and are applied by the PreSync migrate job,
so a seed change needs a pin roll before it exists in the database.

## Canonical metadata: dropped, or never produced

```bash
cd document-intelligence
uv run --extra service python -m document_intelligence.persist.metadata_audit \
  --uri s3://evidara-lakehouse/canonical/published_documents --plan
```

Reports `LOST` / `PRESENT` / `INDETERMINATE`. It refuses to call a key lost
without a witness that something produced it, which is the distinction that keeps
"the struct cannot hold it" separate from "it was discarded". MinIO is in-cluster:
`kubectl -n evidara port-forward svc/minio 19000:9000` and point
`DI_S3_ENDPOINT_URL` at it.

## One document, end to end

```bash
curl -sS "$EVIDARA_LEGAL_SEARCH_URL/v1/documents/$DOC" -H "X-API-Key: $EVIDARA_LEGAL_SEARCH_API_KEY"
# and what the canonical layer holds, from inside the cluster:
kubectl -n evidara exec deploy/document-service -- python3 -c "
import urllib.request,json
print(json.loads(urllib.request.urlopen('http://127.0.0.1:8090/v1/documents/$DOC/lean').read())['title'])"
```

The detail view's fields are `contentLanguage` and `metadata` rows — **not**
`language` or `jurisdiction_ids`. Reading the wrong key once produced a false
report of missing metadata.

```bash
# Records the projection wrote without their enrichment: a fabricated title.
curl -sS "$EVIDARA_LEGAL_SEARCH_URL/v1/search?q=Document&size=1" \
  -H "X-API-Key: $EVIDARA_LEGAL_SEARCH_API_KEY" | python3 -c 'import json,sys; print(json.load(sys.stdin)["totalResults"])'
```

No legitimate title has the shape `Document doc_<id>`.

## Which repo owns an infra file

```bash
python3 scripts/check_platform_ownership.py --list
```

The shared cluster layer lives in `research-platform`. An edit to a frozen file
here **does not reach the cluster** and silently forks the estate. Check before
writing manifests, not after.

## Shell traps that produce wrong answers

- **`pkill -f <pattern>` matches your own command line** and kills the shell
  running it. Use a self-excluding pattern: `pkill -f "1[9]000:9000"`.
- **`git stash` does not stash untracked files.** A "clean main" comparison with
  new files still present measured the wrong tree and produced a false report
  that a lint gate was broken on `main`.
- **Piping a long-running command into `tail` buffers everything**, so a
  background task shows no progress and its exit code is `tail`'s, not the
  command's. A failure read as success.
- **Never edit a script while it is running.** Bash reads incrementally by byte
  offset; an insertion shifts the file under the live interpreter and it dies on
  garbage.
- **`--force` matches `--force-stdin`.** A test forbidding destructive flags by
  substring failed a correct script. Match named operations, not fragments.
