# Runbook — learned-sparse embedding backfill (ADR-0054)

Owner: Platform team
Last reviewed: 2026-09-05
Last verified: **2026-09-05, workstation path only — see [Status](#status)**
Applies to: prod (self-hosted Hetzner k3s, ADR-0029)

## Status

The **workstation path below has been run against the live write alias** and is
reproducible. The **in-cluster GPU Job is a template that has never run**, because
the image it needs is not published — see [Step 4](#step-4--the-in-cluster-gpu-job-not-yet-runnable).

What was proven on 2026-09-05, and nothing beyond it:

| Claim | Evidence |
|---|---|
| torch runs on the workstation GPU | `torch 2.14.0+cu130`, `sm_120`, RTX 5090, matmul on device |
| BGE-M3 loads and encodes on that GPU | 76 chunks over 2 documents, 20.6s including model load |
| `rank_features` accepts the vectors | 2 documents updated, 0 failed, 3,671 features each |
| A sparse query retrieves them | see [Step 5](#step-5--verify) |
| GPU scheduling works in-cluster | a smoke pod printed `NVIDIA GeForce RTX 5090, 32607 MiB` |
| The Job manifest is correct | **not proven** — no image, so it has never been applied |

## What this does

Adds `content_sparse` — a BGE-M3 learned-sparse vector — to documents already in
the search index. It adds one derived field. It does not build a projection, does
not create an index, and does not decide what a document is; those belong to
`ProjectionsService` and to `documents-index.mapping.ts` respectively.

The long-term home for this field is the `document.processed` event, so live
traffic carries it. That is a contract change and is deliberately not made yet:
this backfill exists to prove the representation is servable before a contract is
committed to it (ADR-0054 D8).

## Why sparse and not a dense vector

Not a quality judgement — a hardware one, and it is reversible:

- `index.knn` is a **static** index setting. `documents-000001` and
  `documents-read-*` do not carry it and cannot gain it without a reindex and an
  alias cutover.
- HNSW graphs live in off-heap memory. At BGE-M3's 1024 dims that is roughly
  4.5KB per vector — about 440MB at 100k sections, ~10.6GB at the 2.4M-passage
  scale of the ZHAW benchmark. The OpenSearch node is capped at 2Gi.

`rank_features` is an ordinary Lucene inverted index: addable to a live mapping,
no off-heap cost. See ADR-0054 D10.

## Step 1 — the field must be in the mapping

Canonically, in `legal-search/api/src/core/opensearch/documents-index.mapping.ts`,
then regenerate the JSON:

```bash
cd legal-search/api && npm run mapping:generate
```

Then apply it to the live index. The backfill **refuses to run** against an index
whose mapping lacks the field, rather than letting OpenSearch dynamic-map a shape
nobody agreed on:

```bash
curl -X PUT "$OPENSEARCH/documents-write/_mapping" \
  -H 'Content-Type: application/json' \
  -d '{"properties":{"content_sparse":{"type":"rank_features"}}}'
```

> `rank_features` does not support `exists` queries, so `GET
> /<index>/_mapping/field/content_sparse` — not a search — is how you confirm it
> landed.

## Step 2 — reaching OpenSearch

The service is ClusterIP-only. From a workstation that is itself a cluster node,
the ClusterIP is directly routable:

```bash
kubectl -n evidara get svc opensearch-cluster-master -o jsonpath='{.spec.clusterIP}'
```

From anywhere else, `kubectl port-forward`.

## Step 3 — the workstation path (verified)

```bash
cd document-intelligence
uv run --extra embeddings python -m document_intelligence.jobs.embedding_backfill \
  --opensearch-url "http://$CLUSTER_IP:9200" \
  --index documents-write \
  --batch-size 8
```

`--index documents-write` is the default and the safe choice: writes land on the
write alias, so reads keep serving whatever they served before. `--dry-run`
encodes and reports without writing.

The run prints a JSON report. A run that wrote nothing is not a success — the job
exits non-zero if anything failed, and lists documents skipped for missing
`content` separately from documents that failed to encode.

First run downloads ~2.3GB of model weights.

## Step 4 — the in-cluster GPU Job (not yet runnable)

**Prerequisite that does not exist yet:** the image. `document-intelligence/Dockerfile.embeddings`
builds it — verified 2026-09-05, and it comes out at **21.5GB**. There is
deliberately no `runtime-images.yml` job building that on every push to `main`;
that is a cost decision for the repo owner, not a default. (A likely halving is
noted in the Dockerfile: the CUDA base is probably redundant with the CUDA runtime
torch's own wheel already bundles. Untested.) Until it is built, pushed and pinned to a commit SHA, this manifest stays
here rather than in `infra/hetzner/apps/`: `scripts/check_hetzner_image_pins.py`
correctly refuses an unpinned image under `infra/hetzner/`, and it caught this
exact placeholder.

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: embedding-backfill
  namespace: evidara
  labels:
    app.kubernetes.io/part-of: evidara
spec:
  # A GPU Job that failed twice has a real problem; retrying it a third time just
  # occupies the only GPU in the cluster.
  backoffLimit: 2
  template:
    metadata:
      labels:
        app: embedding-backfill
        app.kubernetes.io/part-of: evidara
    spec:
      restartPolicy: OnFailure

      # See the header: without this the pod schedules and then cannot see the GPU.
      runtimeClassName: nvidia

      nodeSelector:
        gpu: "true"
      tolerations:
        - key: gpu
          operator: Equal
          value: "true"
          effect: NoSchedule

      containers:
        - name: backfill
          image: ghcr.io/philipplukas/evidara-document-intelligence-embeddings:PIN_ME
          args:
            - "--opensearch-url"
            - "http://opensearch-cluster-master:9200"
            # The write alias, so reads keep serving whatever they served before
            # this ran. Promoting is a separate, deliberate act.
            - "--index"
            - "documents-write"
            - "--batch-size"
            - "8"
          resources:
            requests:
              cpu: "2"
              memory: 8Gi
              nvidia.com/gpu: 1
            limits:
              # A GPU is not shareable here: the device plugin allocates whole
              # cards, so request and limit must match or the pod is unschedulable.
              nvidia.com/gpu: 1
              memory: 24Gi
          volumeMounts:
            - name: model-cache
              mountPath: /models
      volumes:
        - name: model-cache
          emptyDir:
            sizeLimit: 16Gi
```

### The three requirements, one of which looks optional

The cluster has one GPU node and it is the workstation:

```
philipp-workstation   32 CPU   63GB   nvidia.com/gpu: 2   label gpu=true
                                      taint  gpu=true:NoSchedule
```

1. **Tolerate the taint** — without it the pod stays Pending.
2. **Select the label** — without it the pod lands on `evidara-k3s` and finds no
   GPU.
3. **`runtimeClassName: nvidia`** — and this is the one that bites. Measured
   2026-09-05: a pod with the label, the toleration and `nvidia.com/gpu: 1` but no
   runtime class **schedules onto the workstation and then dies** with
   `exec: "nvidia-smi": executable file not found in $PATH`. The device plugin
   advertises the cards and the scheduler allocates one, so everything reads as
   configured — but without the runtime class the driver is never injected. With
   it, the same pod prints `NVIDIA GeForce RTX 5090, 32607 MiB`.

## Step 5 — verify

Confirm the vectors are stored and that a query actually retrieves them. Encode
the query with the **same** tokenizer the documents used — the index stores
`t<token-id>` keys, so a query encoded any other way matches nothing while
erroring on nothing.

Measured on the live write alias, 2026-09-05, against a two-document corpus (both
copies of the Bundesverfassung):

| Query | sparse | BM25 |
|---|---|---|
| *Welche Rechte haben Menschen mit Behinderung?* | 0.149 (2 hits) | 0.949 (2 hits) |
| *Wie wird der Bundesrat gewaehlt?* | 0.155 (2 hits) | 0.686 (2 hits) |
| *recipe for chocolate cake* | 0.003 (**2 hits**) | 0.000 (**0 hits**) |

The third row is the point, and it is ADR-0054's central risk observed rather
than argued: **BM25 abstained and sparse did not.** A query with no relationship
to the corpus returned every document in it. The score is two orders of magnitude
lower, which is what makes a threshold possible — and exactly why ADR-0054 D4
makes the abstention gate a first-class, separately tested behaviour rather than
something to add later.

## What this does not prove

- **Nothing about relevance.** Two documents, and they are duplicates of the same
  Bundesverfassung. Ranking quality is not measurable here at any corpus size
  below the point where a query can have a wrong answer available (ADR-0054 D9).
- **Nothing about German-language quality** relative to alternatives. That is D6's
  per-language reporting, and it needs a golden set.
- **Nothing about the Job manifest**, which has never run.
