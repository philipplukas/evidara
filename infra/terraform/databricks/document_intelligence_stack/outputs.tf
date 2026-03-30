output "environment" {
  value = local.environment
}

output "catalog_name" {
  value = module.document_intelligence.catalog_name
}

output "schema_name" {
  value = module.document_intelligence.schema_name
}

output "schema_full_name" {
  value = module.document_intelligence.schema_full_name
}

output "external_location_name" {
  value = module.document_intelligence.external_location_name
}

output "external_location_url" {
  value = module.document_intelligence.external_location_url
}

output "surfaces_root_uri" {
  value = var.external_location_url
}
