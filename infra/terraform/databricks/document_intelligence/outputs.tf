output "catalog_name" {
  value = databricks_catalog.document_intelligence.name
}

output "schema_name" {
  value = databricks_schema.published.name
}

output "schema_full_name" {
  value = "${databricks_catalog.document_intelligence.name}.${databricks_schema.published.name}"
}

output "external_location_name" {
  value = var.create_external_location ? databricks_external_location.document_intelligence_surfaces[0].name : null
}

output "external_location_url" {
  value = var.external_location_url
}
