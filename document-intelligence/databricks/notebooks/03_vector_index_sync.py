# Databricks notebook source
"""Create or refresh the Mosaic AI Vector Search index backing srv_search_chunks.

Uses a Delta Sync Index so the underlying Delta table stays the source of
truth; embedding is delegated to a Databricks foundation-model endpoint
(default: databricks-bge-large-en).

Widgets:
  catalog                     - Unity Catalog name (required).
  schema                      - Schema containing the source table (default: di_marts).
  source_table                - Source table (default: srv_search_chunks).
  vector_endpoint_name        - Vector Search endpoint (required).
  vector_index_name           - Fully qualified index name (required).
  embedding_model_endpoint    - Foundation-model endpoint for embedding
                                (default: databricks-bge-large-en).
  primary_key                 - Source primary key column (default: chunk_id).
  text_column                 - Column to embed (default: chunk_text).
"""

from databricks.vector_search.client import VectorSearchClient  # type: ignore[import-not-found]


def _widget(name: str, default: str = "") -> str:
    try:
        return dbutils.widgets.get(name)  # type: ignore[name-defined]
    except Exception:
        return default


catalog = _widget("catalog")
schema = _widget("schema") or "di_marts"
source_table = _widget("source_table") or "srv_search_chunks"
endpoint_name = _widget("vector_endpoint_name")
index_name = _widget("vector_index_name")
embedding_endpoint = _widget("embedding_model_endpoint") or "databricks-bge-large-en"
primary_key = _widget("primary_key") or "chunk_id"
text_column = _widget("text_column") or "chunk_text"

if not catalog or not endpoint_name or not index_name:
    raise ValueError("catalog, vector_endpoint_name, and vector_index_name are required")

source_fqn = f"{catalog}.{schema}.{source_table}"

client = VectorSearchClient()

endpoints = {ep.get("name") for ep in client.list_endpoints().get("endpoints", [])}
if endpoint_name not in endpoints:
    print({"step": "create_endpoint", "name": endpoint_name})
    client.create_endpoint(name=endpoint_name, endpoint_type="STANDARD")

existing = {ix.get("name") for ix in client.list_indexes(name=endpoint_name).get("vector_indexes", [])}

if index_name not in existing:
    print({"step": "create_index", "name": index_name, "source": source_fqn})
    client.create_delta_sync_index(
        endpoint_name=endpoint_name,
        source_table_name=source_fqn,
        index_name=index_name,
        pipeline_type="TRIGGERED",
        primary_key=primary_key,
        embedding_source_column=text_column,
        embedding_model_endpoint_name=embedding_endpoint,
    )
else:
    print({"step": "sync_index", "name": index_name})
    index = client.get_index(endpoint_name=endpoint_name, index_name=index_name)
    index.sync()

print({"status": "vector_index_sync_completed", "index": index_name})
