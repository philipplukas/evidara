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

output "compute_guardrails_cluster_policy_id" {
  description = "Databricks cluster policy id when enable_databricks_compute_guardrails is true."
  value       = var.enable_databricks_compute_guardrails ? databricks_cluster_policy.compute_guardrails[0].id : null
}

output "compute_guardrails_cluster_policy_display_name" {
  description = "Cluster policy display name used by the Asset Bundle lookup (must match document-intelligence/databricks.yml)."
  value       = var.enable_databricks_compute_guardrails ? local.compute_guardrails_cluster_policy_display_name : null
}
