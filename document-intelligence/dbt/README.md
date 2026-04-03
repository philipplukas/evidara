# dbt scaffold

This folder provides an initial dbt project scaffold for document-intelligence.

## Current intent

- Keep dbt setup explicit and versioned in-repo.
- Start with thin staging and mart models over published surfaces.
- Allow CI/runtime wiring to be added incrementally.

## Next steps

- Add a profile strategy for your Databricks environment(s).
- Wire `dbt deps` and `dbt build` into CI once credentials are available.
- Expand tests in `models/**/schema.yml` as table contracts stabilize.
