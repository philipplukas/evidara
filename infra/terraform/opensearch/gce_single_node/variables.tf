variable "environment" {
  description = "Target Evidara environment."
  type        = string

  validation {
    condition     = contains(["dev", "staging", "prod"], lower(var.environment))
    error_message = "environment must be one of dev, staging, or prod."
  }
}

variable "project_id" {
  description = "GCP project ID."
  type        = string
}

variable "region" {
  description = "GCP region for the VM."
  type        = string
}

variable "zone" {
  description = "GCP zone for the VM."
  type        = string
}

variable "machine_type" {
  description = "GCE machine type.  e2-small (2 vCPU, 2 GB) is the minimum for OpenSearch."
  type        = string
  default     = "e2-medium"
}

variable "disk_size_gb" {
  description = "Persistent disk size in GB for OpenSearch data."
  type        = number
  default     = 30
}

variable "opensearch_version" {
  description = "OpenSearch Docker image tag."
  type        = string
  default     = "2.17.1"
}

variable "opensearch_heap_size" {
  description = "JVM heap size for OpenSearch (Xms/Xmx)."
  type        = string
  default     = "512m"
}

variable "network" {
  description = "VPC network self-link or name. Uses 'default' if not specified."
  type        = string
  default     = "default"
}

variable "subnetwork" {
  description = "VPC subnetwork self-link or name. Leave null to use auto-subnet."
  type        = string
  default     = null
  nullable    = true
}

variable "allowed_source_ranges" {
  description = "CIDR ranges allowed to reach OpenSearch (port 9200). Restrict to Cloud Run VPC connector subnet and bastion/admin IPs."
  type        = list(string)
  default     = ["10.0.0.0/8"]
}

variable "service_name_override" {
  description = "Optional base name override. Defaults to evidara-opensearch-<env>."
  type        = string
  default     = null
  nullable    = true
}
