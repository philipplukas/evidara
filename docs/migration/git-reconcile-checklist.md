# Git reconcile checklist (post–MacConfig platform merge)

Use this after MacConfig `main` gains `clusters/prod/platform-contract.yaml` and related
platform scaffolding, and after you merge the Evidara branch that vendors the contract.

## Goals

- One copy of each scaffold (no duplicate `platform-contract` or K8s snippets committed twice).
- `main` is the integration branch; long-lived feature branches replay cleanly on top.

## Steps

1. **Fetch and update local `main`**

   ```bash
   git fetch origin
   git checkout main
   git pull origin main
   ```

2. **Reconcile your feature branch**

   ```bash
   git checkout <your-branch>
   git rebase origin/main   # or: git merge origin/main
   ```

3. **Drop duplicate artifacts**

   - If the branch still contains copies of files that now live only in **MacConfig** (for example
     a second `platform-contract.yaml` outside `vendor/`), delete them in the rebase/merge resolution.
   - If you had experimental `clusters/` or Argo YAML in Evidara that MacConfig now owns, remove
     those copies and link to MacConfig in docs instead.

4. **Re-run local gates**

   ```bash
   pre-commit run --all-files   # optional but thorough
   bash scripts/check_docs.sh
   ```

5. **Open / refresh the PR**

   - Ensure the diff is only intentional files (vendor pin, docs, Terraform, workflows you mean to ship).

## MacConfig side (same merge window)

- Confirm `make platform-contract-path` prints the file you vendored into Evidara.
- Run MacConfig’s own CI (`make platform-k8s-check` or equivalent) on `main` after the platform PR merges.
