variable "environment" {
  description = "Target Evidara environment."
  type        = string

  validation {
    condition     = contains(["dev", "staging", "prod"], lower(var.environment))
    error_message = "environment must be one of dev, staging, or prod."
  }
}

variable "project_id" {
  description = "GCP project ID where runtime resources are provisioned."
  type        = string
}

variable "region" {
  description = "Default region for Pub/Sub and any regionalized runtime resources."
  type        = string
}

variable "bucket_location" {
  description = "Location/region for GCS buckets."
  type        = string
  default     = "EU"
}

variable "raw_artifact_bucket_name" {
  description = "Optional override for the raw artifact bucket name."
  type        = string
  default     = null
  nullable    = true
}

variable "manifest_bucket_name" {
  description = "Optional override for the immutable manifest bucket name."
  type        = string
  default     = null
  nullable    = true
}

variable "bucket_force_destroy" {
  description = "Whether objects may be destroyed when deleting buckets."
  type        = bool
  default     = false
}

variable "event_topic_names" {
  description = "Base Pub/Sub topic names for the runtime event mesh."
  type        = set(string)
  default = [
    "artifact-bundle-available",
    "raw-artifact-available",
    "document-processing-status-updated",
    "document-processed",
    "document-withdrawn",
    "index-update-requested",
  ]
}

variable "event_subscriptions" {
  description = "Subscription definitions keyed by base subscription name."
  type = map(object({
    topic_name                 = string
    ack_deadline_seconds       = optional(number, 20)
    message_retention_duration = optional(string, "604800s")
  }))
  default = {
    "document-intelligence-artifact-bundle-available" = {
      topic_name = "artifact-bundle-available"
    }
    "platform-control-document-processing-status-updated" = {
      topic_name = "document-processing-status-updated"
    }
    "legal-search-document-processed" = {
      topic_name = "document-processed"
    }
    "legal-search-document-withdrawn" = {
      topic_name = "document-withdrawn"
    }
    "legal-search-index-update-requested" = {
      topic_name = "index-update-requested"
    }
  }
}

variable "enable_cloud_sql" {
  description = "Whether to provision the Cloud SQL Postgres instance for platform-control."
  type        = bool
  default     = false
}

variable "cloud_sql_tier" {
  description = "Machine tier for Cloud SQL Postgres instance."
  type        = string
  default     = "db-custom-1-3840"
}

variable "cloud_sql_disk_size_gb" {
  description = "Disk size (GB) for the Cloud SQL instance."
  type        = number
  default     = 20
}

variable "platform_control_database_name" {
  description = "Primary database name for platform-control."
  type        = string
  default     = "platform_control"
}

variable "runtime_service_account_ids" {
  description = "Service account IDs for runtime services."
  type        = map(string)
  default = {
    platform_control_api    = "evidara-platform-control-api"
    platform_control_worker = "evidara-platform-control-worker"
    legal_search_api        = "evidara-legal-search-api"
    legal_search_frontend   = "evidara-legal-search-frontend"
    document_intelligence   = "evidara-document-intelligence"
  }
}

variable "cloud_run_services" {
  description = "Cloud Run service configuration keyed by service name."
  type = map(object({
    image                 = string
    service_account_key   = string
    container_port        = optional(number, 8080)
    ingress               = optional(string, "INGRESS_TRAFFIC_ALL")
    allow_unauthenticated = optional(bool, false)
    min_instance_count    = optional(number, 0)
    max_instance_count    = optional(number, 2)
    cpu                   = optional(string, "1")
    memory                = optional(string, "512Mi")
    timeout_seconds       = optional(number, 300)
    vpc_connector         = optional(string, null)
    vpc_egress            = optional(string, "PRIVATE_RANGES_ONLY")
    env_vars              = optional(map(string), {})
    secret_env_vars = optional(map(object({
      secret_name = string
      version     = optional(string, "latest")
    })), {})
  }))
  default = {}
}

variable "runtime_secret_ids" {
  description = "Secret Manager secret IDs required by runtime services."
  type        = map(string)
  default = {
    opensearch_node      = "opensearch-node"
    opensearch_username  = "opensearch-username"
    opensearch_password  = "opensearch-password"
    firecrawl_api_key    = "firecrawl-api-key"
    firecrawl_webhook    = "firecrawl-webhook-secret"
    platform_control_dsn = "platform-control-database-url"
  }
}
