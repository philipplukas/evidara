locals {
  environment            = lower(var.environment)
  catalog_name           = coalesce(var.catalog_name, "evidara_document_intelligence_${local.environment}")
  schema_name            = coalesce(var.schema_name, "published")
  schema_comment         = coalesce(var.schema_comment, "Published canonical surfaces for Evidara document-intelligence (${local.environment}).")
  external_location_name = coalesce(var.external_location_name, "evidara_document_intelligence_surfaces_${local.environment}")
}

module "document_intelligence" {
  source = "../document_intelligence"

  catalog_name             = local.catalog_name
  schema_name              = local.schema_name
  schema_comment           = local.schema_comment
  external_location_name   = local.external_location_name
  external_location_url    = var.external_location_url
  storage_credential_name  = var.storage_credential_name
  create_external_location = var.create_external_location
  catalog_grants           = var.catalog_grants
  schema_grants            = var.schema_grants
  external_location_grants = var.external_location_grants
}
