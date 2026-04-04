output "opensearch_internal_ip" {
  description = "Internal IP address of the OpenSearch GCE instance."
  value       = google_compute_instance.opensearch.network_interface[0].network_ip
}

output "opensearch_instance_name" {
  description = "Name of the GCE instance."
  value       = google_compute_instance.opensearch.name
}

output "opensearch_endpoint" {
  description = "HTTP endpoint for OpenSearch (internal only, no TLS)."
  value       = "http://${google_compute_instance.opensearch.network_interface[0].network_ip}:9200"
}
