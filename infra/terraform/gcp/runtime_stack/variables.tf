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

variable "project_number" {
  description = "Optional GCP project number; set to avoid project data-source lookup during plan."
  type        = string
  default     = null
  nullable    = true
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

variable "artifact_bundle_subscription_push" {
  description = <<-EOT
    When set, merges push_config onto an existing subscription (matched by map key in event_subscriptions)
    so Pub/Sub delivers artifact-bundle events to the HTTP DI ingress Cloud Run service.
    Example: subscription_key = "document-intelligence-artifact-bundle-available", target_service = "di-consumer".
  EOT
  type = object({
    subscription_key = string
    target_service   = string
    endpoint_path    = optional(string, "/internal/events/artifact-bundles:process")
  })
  default  = null
  nullable = true
}

variable "document_intelligence_published_bucket_name" {
  description = <<-EOT
    GCS bucket for DI published Delta surfaces (e.g. evidara-document-intelligence-surfaces-dev).
    When set, grants the document_intelligence runtime service account roles/storage.objectAdmin on this bucket.
    The bucket may live outside this module; it must already exist.
  EOT
  type        = string
  default     = null
  nullable    = true
}

variable "event_subscriptions" {
  description = "Subscription definitions keyed by base subscription name."
  type = map(object({
    topic_name                 = string
    ack_deadline_seconds       = optional(number, 20)
    message_retention_duration = optional(string, "604800s")
    retry_policy = optional(object({
      minimum_backoff = optional(string, "10s")
      maximum_backoff = optional(string, "600s")
    }), null)
    dead_letter_policy = optional(object({
      max_delivery_attempts = optional(number, 10)
    }), null)
    # Push subscription config (omit for pull subscriptions)
    push_config = optional(object({
      # Cloud Run service key (from cloud_run_services map) to push to
      target_service = string
      # Path on the target service (e.g. "/v1/projections/events/document-processed")
      endpoint_path = string
    }), null)
  }))
  default = {
    "document-intelligence-artifact-bundle-available" = {
      topic_name           = "artifact-bundle-available"
      ack_deadline_seconds = 120
      retry_policy         = { minimum_backoff = "30s", maximum_backoff = "600s" }
      dead_letter_policy   = { max_delivery_attempts = 10 }
    }
    "platform-control-document-processing-status-updated" = {
      topic_name         = "document-processing-status-updated"
      retry_policy       = { minimum_backoff = "10s", maximum_backoff = "300s" }
      dead_letter_policy = { max_delivery_attempts = 5 }
      push_config = {
        target_service = "platform-control-api"
        endpoint_path  = "/v1/di/events/document-processing-status-updated"
      }
    }
    "platform-control-document-processed" = {
      topic_name         = "document-processed"
      retry_policy       = { minimum_backoff = "10s", maximum_backoff = "300s" }
      dead_letter_policy = { max_delivery_attempts = 5 }
      push_config = {
        target_service = "platform-control-api"
        endpoint_path  = "/v1/di/events/document-processed"
      }
    }
    "legal-search-document-processed" = {
      topic_name         = "document-processed"
      retry_policy       = { minimum_backoff = "10s", maximum_backoff = "300s" }
      dead_letter_policy = { max_delivery_attempts = 5 }
      push_config = {
        target_service = "legal-search-api"
        endpoint_path  = "/v1/projections/events/document-processed"
      }
    }
    "legal-search-document-withdrawn" = {
      topic_name         = "document-withdrawn"
      retry_policy       = { minimum_backoff = "10s", maximum_backoff = "300s" }
      dead_letter_policy = { max_delivery_attempts = 5 }
      push_config = {
        target_service = "legal-search-api"
        endpoint_path  = "/v1/projections/events/document-withdrawn"
      }
    }
    "legal-search-index-update-requested" = {
      topic_name         = "index-update-requested"
      retry_policy       = { minimum_backoff = "10s", maximum_backoff = "300s" }
      dead_letter_policy = { max_delivery_attempts = 5 }
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
    platform_control_admin  = "evidara-platform-control-admin"
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
    cloud_sql_instances   = optional(list(string), [])
    startup_probe_path    = optional(string, null)
    liveness_probe_path   = optional(string, null)
    env_vars              = optional(map(string), {})
    secret_env_vars = optional(map(object({
      secret_name = string
      version     = optional(string, "latest")
    })), {})
  }))
  default = {}
}

variable "cloud_run_jobs" {
  description = "Cloud Run job configuration keyed by job name."
  type = map(object({
    image               = string
    service_account_key = string
    command             = optional(list(string), [])
    args                = optional(list(string), [])
    timeout_seconds     = optional(number, 900)
    max_retries         = optional(number, 1)
    vpc_connector       = optional(string, null)
    vpc_egress          = optional(string, "PRIVATE_RANGES_ONLY")
    cloud_sql_instances = optional(list(string), [])
    env_vars            = optional(map(string), {})
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
    opensearch_node               = "opensearch-node"
    opensearch_username           = "opensearch-username"
    opensearch_password           = "opensearch-password"
    document_service_bearer_token = "document-service-bearer-token"
    firecrawl_api_key             = "firecrawl-api-key"
    firecrawl_webhook             = "firecrawl-webhook-secret"
    platform_control_dsn          = "platform-control-database-url"
  }
}

# --- Optional billing guardrails (see billing_guardrails.tf) ---

variable "enable_billing_budget" {
  description = "When true, create a Cloud Billing budget scoped to this project."
  type        = bool
  default     = false
}

variable "billing_account_id" {
  description = "GCP billing account ID (format 012345-67890A-BCEDF0). Required when enable_billing_budget is true."
  type        = string
  default     = ""
}

variable "billing_budget_amount_units" {
  description = "Whole currency units for the monthly project budget (string for API compatibility, e.g. \"500\")."
  type        = string
  default     = "500"
}

variable "billing_budget_currency_code" {
  description = "ISO 4217 currency code for the budget amount."
  type        = string
  default     = "EUR"
}

variable "billing_budget_threshold_percentages" {
  description = "Alert thresholds as fractions of the budget (0–1, for example 0.5 for 50%)."
  type        = list(number)
  default     = [0.5, 0.8, 1.0]

  validation {
    condition = alltrue([
      for p in var.billing_budget_threshold_percentages : p > 0 && p <= 1
    ])
    error_message = "Each billing_budget_threshold_percentages entry must be in (0, 1]."
  }
}

variable "billing_budget_notification_emails" {
  description = "Extra alert recipients via Cloud Monitoring email channels in this project (in addition to billing admins unless disabled). When non-empty, an all_updates_rule is created; GCP allows at most five channels."
  type        = list(string)
  default     = []

  validation {
    condition     = length(var.billing_budget_notification_emails) <= 5
    error_message = "billing_budget_notification_emails may contain at most five addresses (GCP limit)."
  }
}

variable "billing_budget_enable_project_level_recipients" {
  description = "When custom notification emails are set, also notify Cloud project Owners for this single-project budget."
  type        = bool
  default     = true
}

variable "billing_budget_disable_default_iam_recipients" {
  description = "When true, billing account admins do not receive budget alerts by default; use billing_budget_notification_emails instead."
  type        = bool
  default     = false
}

# --- Monitoring & alerting (see monitoring.tf) ---

variable "enable_monitoring" {
  description = "Whether to provision alert policies and notification channels."
  type        = bool
  default     = true
}

variable "monitoring_notification_email" {
  description = "Email address for alert notifications. Leave empty to skip email channel."
  type        = string
  default     = ""
}

variable "monitoring_slack_webhook_url" {
  description = "Slack webhook URL for alert notifications. Leave empty to skip."
  type        = string
  default     = ""
  sensitive   = true
}

variable "cloud_sql_max_connections" {
  description = "Expected max_connections for the Cloud SQL instance (depends on tier). Used to compute the 80% alert threshold."
  type        = number
  default     = 200
}
