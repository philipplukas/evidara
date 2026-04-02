# Published Surface Registration

This directory documents the SQL/bootstrap path for registering the published DI Delta surfaces in Unity Catalog.

## Why this exists

The Delta datasets are physically written by the DI runtime, but we do not want Terraform to own the evolving table metadata during early development.

So the current split is:

- Terraform creates the stable Unity Catalog scaffolding
- the DI job writes Delta data
- a small SQL/bootstrap step registers the published tables against those Delta locations

## Render the SQL

From [`../`](../):

```bash
python3 -m document_intelligence.bootstrap.register_surfaces \
  --catalog-name document_intelligence \
  --schema-name published \
  --surfaces-root-uri gs://evidara-di-dev/published
```

Or through the installed script entrypoint:

```bash
document_intelligence_render_surface_sql \
  --catalog-name document_intelligence \
  --schema-name published \
  --surfaces-root-uri gs://evidara-di-dev/published
```

The rendered SQL creates or registers:

- `published_documents`
- `published_sections`
- `processing_manifests`

using `CREATE TABLE IF NOT EXISTS ... USING DELTA LOCATION ...`.
