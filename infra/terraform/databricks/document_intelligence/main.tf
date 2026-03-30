locals {
  schema_full_name = "${databricks_catalog.document_intelligence.name}.${databricks_schema.published.name}"
}

resource "databricks_catalog" "document_intelligence" {
  name    = var.catalog_name
  comment = "Catalog for Evidara document-intelligence published surfaces."
}

resource "databricks_schema" "published" {
  catalog_name = databricks_catalog.document_intelligence.name
  name         = var.schema_name
  comment      = var.schema_comment
}

resource "databricks_external_location" "document_intelligence_surfaces" {
  count           = var.create_external_location ? 1 : 0
  name            = var.external_location_name
  url             = var.external_location_url
  credential_name = var.storage_credential_name
  comment         = "External location for document-intelligence published surfaces."
  skip_validation = true
  read_only       = false
}

resource "databricks_grants" "catalog" {
  catalog = databricks_catalog.document_intelligence.name

  dynamic "grant" {
    for_each = var.catalog_grants
    content {
      principal  = grant.value.principal
      privileges = grant.value.privileges
    }
  }
}

resource "databricks_grants" "schema" {
  schema = local.schema_full_name

  dynamic "grant" {
    for_each = var.schema_grants
    content {
      principal  = grant.value.principal
      privileges = grant.value.privileges
    }
  }
}

resource "databricks_grants" "external_location" {
  count             = var.create_external_location ? 1 : 0
  external_location = databricks_external_location.document_intelligence_surfaces[0].name

  dynamic "grant" {
    for_each = var.external_location_grants
    content {
      principal  = grant.value.principal
      privileges = grant.value.privileges
    }
  }
}
