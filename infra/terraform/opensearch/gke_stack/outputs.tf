output "environment" {
  value = local.environment
}

output "network_name" {
  value = google_compute_network.opensearch.name
}

output "subnet_name" {
  value = google_compute_subnetwork.opensearch.name
}

output "gke_cluster_name" {
  value = google_container_cluster.opensearch.name
}

output "vpc_connector_name" {
  value = google_vpc_access_connector.opensearch.name
}

output "vpc_connector_id" {
  value = google_vpc_access_connector.opensearch.id
}

output "service_name" {
  value = local.base_name
}

output "service_uri" {
  value       = local.opensearch_internal_endpoint_host == null ? null : "https://${local.opensearch_internal_endpoint_host}:9200"
  description = "Internal OpenSearch endpoint URI for runtime clients."
}

output "service_host" {
  value = local.opensearch_internal_endpoint_host
}

output "service_port" {
  value = 9200
}

output "service_username" {
  value = "admin"
}

output "service_password" {
  value       = random_password.opensearch_admin.result
  sensitive   = true
  description = "Generated OpenSearch admin password."
}
