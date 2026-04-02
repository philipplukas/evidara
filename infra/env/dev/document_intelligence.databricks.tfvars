environment = "dev"

workspace_host = "https://dbc-0000000000000000.cloud.databricks.com"

external_location_url = "gs://evidara-document-intelligence-surfaces-dev/published"
storage_credential_name = "evidara_document_intelligence_dev"

catalog_grants = [
  {
    principal  = "document-intelligence-dev"
    privileges = ["USE_CATALOG", "CREATE_SCHEMA"]
  },
  {
    principal  = "legal-search-dev"
    privileges = ["USE_CATALOG"]
  },
]

schema_grants = [
  {
    principal  = "document-intelligence-dev"
    privileges = ["USE_SCHEMA", "CREATE_TABLE", "MODIFY", "SELECT"]
  },
  {
    principal  = "legal-search-dev"
    privileges = ["USE_SCHEMA", "SELECT"]
  },
]

external_location_grants = [
  {
    principal  = "document-intelligence-dev"
    privileges = ["CREATE_EXTERNAL_TABLE", "READ_FILES", "WRITE_FILES"]
  },
]
