# ADR-0055: Argo CD syncs `infra/hetzner/apps`, and the second manifest tree is retired

## Status

Proposed

## Date

2026-09-06

## Context

### Production drifted 27 commits behind, and nothing in the system noticed

On 2026-09-06 the Hetzner cluster was running `4dddce3c`, pinned on 2026-09-04. `main` was
27 commits ahead. Every image needed to move forward had been built and pushed to GHCR the
whole time — the gap was not a build failure, it was that **nothing applies the manifests
unless a human runs a script**.

`infra/hetzner/apps/kustomization.yaml` is the source of truth for what should run.
`infra/hetzner/deploy-stage4.sh` is what makes it true. Between a merge to `main` and that
script being run by hand, the repository and the cluster disagree, and the only way to learn
by how much is to ask the cluster.

That is not a discipline problem to be solved with a reminder. It is the absence of a
controller.

### The prior roll had the same shape

The pin before this one (`8759bec5`, 2026-07-23) sat for **35 commits**. Its successor's
commit message records that three of those were user-visible in `search.evidara.veyo.dev` and
"had shipped to nobody" (#879). Two data points, same cause.

### There are already two manifest trees, and the aspirational one is the one CI checks

| Tree | Workloads | Applied by | Describes this cluster? |
|---|---|---|---|
| `infra/hetzner/apps/` | 6 | `deploy-stage4.sh`, by hand | yes — it is what runs |
| `k8s/gitops/{base,dev,staging,prod}` | 10 | nothing | no |

`k8s/gitops/` was authored in ADR-0029 Slice 5 for a MacConfig-managed platform that this
deployment did not become. Measured 2026-09-06:

- it targets namespaces `evidare-dev`, `evidare-staging`, `evidare-prod`. None exist. The live
  namespace is `evidara` — the tree is not merely unapplied, it is misspelled.
- its `ExternalSecret`s reference a `shared-vault` `ClusterSecretStore` that is not installed;
  the real secrets are created imperatively by `deploy-stage4.sh`.
- its ingress hosts are still the placeholders `*.dev.evidara.example`.
- it assumes Postgres, OpenSearch, NATS and MinIO are platform-provided at
  `*.evidara-platform.svc`. All four run inside `evidara` in this cluster.

So the repository declares a GitOps layout, and a reader — human or agent — reasonably
concludes GitOps is how this deploys. It is not. This is ADR-0052 exactly: *declared and
unproduced reads as an answer, not as a question.*

### And the gate over it cannot fail where it matters

`scripts/validate_k8s_gitops_kustomize.sh` renders all three env roots and prints
**`OK: all k8s/gitops kustomizations render.`** But `k8s/gitops/prod/kustomization.yaml` is
`resources: []` — deliberately, pending an activation that never happened. The gate therefore
reports success over an overlay that renders **nothing**, for the environment that matters
most. ADR-0051: a gate that cannot fail is not a gate.

## Decision

**1. Install Argo CD, and point it at `infra/hetzner/apps` — the tree that works.**

Not at `k8s/gitops/`. Reviving a tree that names the wrong namespaces, the wrong secret
backend and placeholder hosts would mean debugging an aspiration; `infra/hetzner/apps` is
already proven against this cluster on every roll since ADR-0029 stage 4.

Argo CD rather than Flux because the cluster already runs Argo Workflows, so the operator is
reading one project's conventions rather than two.

**2. Migrations become a `PreSync` hook, not a separate script step.**

`deploy-stage4.sh` runs `migrate-job.yaml`, waits for completion, and only then applies the
kustomization. That ordering is the whole reason the migrate Job is deliberately outside the
`images:` transformer, and it must survive the move. Argo CD's `PreSync` hook is exactly this
guarantee, expressed declaratively: the sync fails and the workloads do not roll if the
migration does not complete.

The Job keeps its hand-maintained tag and
`scripts/check_hetzner_image_pins.py` keeps enforcing lockstep with the `images:` pin — the
hook changes when it runs, not how it is versioned.

**3. `k8s/gitops/` is deleted, not fixed.**

Two trees for one cluster is ADR-0050's failure (one rule, one enforcement point): the easier
path becomes the real policy and it is usually the weaker one. Nothing references
`k8s/gitops/` outside its own README and its own CI gate, and no environment it describes
exists. Retaining it "in case staging comes back" preserves a description of a platform this
project did not adopt.

The staging/dev intent it encoded is not lost — it is the `Application` per environment that
replaces it, authored against real namespaces when those environments exist.

`scripts/validate_k8s_gitops_kustomize.sh` is replaced by a gate over
`infra/hetzner/apps` — a tree with no empty overlay, so the gate can fail.

**4. Automatic sync, with pruning off initially.**

`syncPolicy.automated.selfHeal: true` closes the drift window this ADR exists to close.
`prune: false` for the first phase: the namespace contains resources Argo does not own
(imperative Secrets, Helm-installed NATS/MinIO/OpenSearch/Trino/Nessie/Zitadel, CNPG), and a
pruning controller meeting them for the first time is not a risk worth taking on day one.
Revisit once `Application` ownership is observed to be correct.

## Consequences

**The pin becomes the deploy.** Merging a change to `infra/hetzner/apps/kustomization.yaml`
rolls production. #883's two-step ("bump the pin, then run `deploy-stage4.sh`") becomes one
step, and the rollout instructions in that file's comment must say so.

**A stale pin is now visible rather than inferred.** Argo CD reports `OutOfSync` when the
cluster and the repository disagree, which is the signal that was missing for 35 commits and
then 27.

**Rollback changes shape.** Today: edit the tag, re-run the script. With Argo CD: revert the
commit, or `argocd app rollback` to a previous sync. Both are recorded in the runbook; the
git revert is the one that keeps the repository honest.

**`deploy-stage4.sh` does not disappear.** It still creates the imperative Secrets and the
GHCR pull secret, which Argo CD does not manage and which must exist before a sync can
succeed. It loses only the migrate-and-apply steps. A cluster still bootstraps by running it
once.

**One tree, one gate.** After this, "what should be running" has exactly one answer in the
repository, and the gate over it renders six real workloads rather than reporting OK over an
empty file.

## Alternatives considered

**Flux.** Equivalent capability. Rejected only because Argo Workflows is already here and a
second Argo-family component costs less operator context than a first Flux one.

**Revive `k8s/gitops/`.** Rejected: every environmental assumption in it is false for this
cluster, so "revive" means "rewrite against `infra/hetzner/apps`'s facts" — at which point the
tree is not being revived, it is being replaced by the thing it would have to copy.

**Keep both trees, sync `k8s/gitops/`.** Rejected under ADR-0050. It also inverts the
evidence: the unproven tree would become authoritative over the one with a deployment history.

**A CI job that runs `deploy-stage4.sh` on merge.** Cheaper, and it would have closed the
27-commit gap. Rejected because it gives push-based deployment with no continuous
reconciliation: drift introduced by anything other than that job — a manual `kubectl edit`, a
failed partial apply — stays invisible exactly as it does today. `selfHeal` is the property
being bought, not automation of the apply.

## References

- ADR-0029 — self-hosted Hetzner runtime; this amends its Slice 5 GitOps layout
- ADR-0050 — one rule, one enforcement point
- ADR-0051 — a gate that cannot fail is not a gate
- ADR-0052 — declared means produced
- #879, #883 — the two stale-pin rolls that motivated this
