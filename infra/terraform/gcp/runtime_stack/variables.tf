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
