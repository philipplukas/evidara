variable "environment" {
  description = "Target Evidara environment."
  type        = string

  validation {
    condition     = contains(["dev", "staging", "prod"], lower(var.environment))
    error_message = "environment must be one of dev, staging, or prod."
  }
}

variable "project_id" {
  description = "GCP project id where network, GKE and OpenSearch are provisioned."
  type        = string
}

variable "region" {
  description = "Primary GCP region for GKE and networking."
  type        = string
}

variable "node_locations" {
  description = "Optional zone list for node placement."
  type        = list(string)
  default     = []
}

variable "gke_release_channel" {
  description = "GKE release channel."
  type        = string
  default     = "REGULAR"
}

variable "cluster_min_master_version" {
  description = "Optional minimum GKE control plane version."
  type        = string
  default     = null
  nullable    = true
}

variable "node_machine_type" {
  description = "Machine type for OpenSearch node pool."
  type        = string
  default     = "e2-standard-4"
}

variable "node_disk_size_gb" {
  description = "Node disk size in GB."
  type        = number
  default     = 200
}

variable "node_count" {
  description = "Node count for OpenSearch pool."
  type        = number
  default     = 3
}

variable "opensearch_namespace" {
  description = "Kubernetes namespace where OpenSearch is installed."
  type        = string
  default     = "opensearch"
}

variable "opensearch_chart_version" {
  description = "Helm chart version for OpenSearch."
  type        = string
  default     = "2.32.0"
}

variable "opensearch_replicas" {
  description = "OpenSearch replica count in Helm values."
  type        = number
  default     = 3
}

variable "opensearch_heap_size" {
  description = "JVM heap size passed to OpenSearch pods."
  type        = string
  default     = "2g"
}

variable "opensearch_persistence_size" {
  description = "PVC size for OpenSearch data nodes."
  type        = string
  default     = "200Gi"
}

variable "vpc_connector_cidr" {
  description = "CIDR range for Serverless VPC Access connector."
  type        = string
  default     = "10.8.0.0/28"
}

variable "service_name_override" {
  description = "Optional base resource name override."
  type        = string
  default     = null
  nullable    = true
}
