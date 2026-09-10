# Contract changesets

One file per contract change. `contracts/manifest.yaml`'s top-level `version` is
**not** hand-edited any more; it is computed from these at release.

## Why

That key is a single scalar every contract PR used to edit, which serialised the
repo — #913 named it as a blocker to running lanes in parallel. Two measured
failure modes:

- Two PRs picking **different** successors (`--minor` → 2.42.0 vs `--patch` →
  2.41.1) conflict textually, along with the changelog comment block above the key.
- Two PRs picking the **same** successor merge cleanly and then fail the gate,
  because the old comparison was against the *tip of the base branch*, not the
  merge base: once PR A landed 2.42.0, PR B's identical, already-correct 2.42.0
  read as "did not change" and had to be redone after rebase.

Two PRs write two different files here, so neither happens.

## Writing one

    python3 scripts/bump_contract_version.py --minor --summary "what changed"

Add `--api` when the platform-control OpenAPI surface changed — that number is
pinned to the app (it must equal the generated spec's `info.version`) and still
moves in the PR. Add `--breaking` when a consumer that ignores the change breaks.

## Format

```yaml
bump: minor      # minor | patch
additive: true   # false when a consumer must change to keep working
summary: >-
  What changed on the locked surface, in prose. At least 20 characters —
  the version number alone tells a reader nothing.
```

`scripts/check_contract_version_bump.py` validates **every** file in this
directory on every run, not only the ones a PR touched.

## Releasing

    python3 scripts/release_contract_version.py --check   # what is pending
    python3 scripts/release_contract_version.py           # cut the version

This bumps the manifest version (`minor` if any pending changeset is `minor`,
else `patch`), prepends the changelog lines, and deletes the consumed files.
It is the only writer of that key.
