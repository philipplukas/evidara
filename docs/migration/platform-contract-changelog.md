# Platform contract changelog (vendored MacConfig)

Tracks **intentional** bumps to [`../../vendor/platform-contract.yaml`](../../vendor/platform-contract.yaml)
(`contractVersion`) after copying from MacConfig `clusters/prod/platform-contract.yaml`.

## How to record a bump

1. In MacConfig: merge the contract change; run `make platform-contract-path`; copy the file into
   `vendor/platform-contract.yaml` in Evidara.
2. Update the README pin line (**Pinned MacConfig platform contract:** `x.y.z`).
3. Add a row below (semver order, newest first).

## Changelog

| `contractVersion` | Date (approx.) | Summary |
| --- | --- | --- |
| `0.1.0` | 2026-04 | Initial vendor from MacConfig `main`; baseline namespaces, ingress, ESO store, allowed/forbidden kinds. |
