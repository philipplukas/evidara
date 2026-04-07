# --------------------------------------------------------------------------
# Monitoring & Alerting — SLO-backed alert policies
#
# Provisions Cloud Monitoring alert policies and notification channels
# for the Evidara runtime stack.
#
# See docs/adr/sli-slo-definitions.md for SLI/SLO definitions.
# --------------------------------------------------------------------------

# --- Variables ---

variable "enable_monitoring" {
  description = "Whether to provision alert policies and notification channels."
  type        = bool
  default     = false
}

variable "monitoring_notification_email" {
  description = "Email address for alert notifications."
  type        = string
  default     = ""
}

variable "monitoring_slack_webhook_url" {
  description = "Slack webhook URL for alert notifications. Leave empty to skip."
  type        = string
  default     = ""
  sensitive   = true
}

# --- Notification channels ---

resource "google_monitoring_notification_channel" "email" {
  count = var.enable_monitoring && var.monitoring_notification_email != "" ? 1 : 0

  display_name = "Evidara Alerts – Email (${local.environment})"
  type         = "email"
  labels = {
    email_address = var.monitoring_notification_email
  }
}

resource "google_monitoring_notification_channel" "slack" {
  count = var.enable_monitoring && var.monitoring_slack_webhook_url != "" ? 1 : 0

  display_name = "Evidara Alerts – Slack (${local.environment})"
  type         = "slack"
  labels = {
    channel_name = "#evidara-alerts"
  }
  sensitive_labels {
    auth_token = var.monitoring_slack_webhook_url
  }
}

locals {
  notification_channels = concat(
    [for ch in google_monitoring_notification_channel.email : ch.id],
    [for ch in google_monitoring_notification_channel.slack : ch.id],
  )
}

# --- Tier 1: DLQ depth (> 0 messages for 15 minutes) ---

resource "google_monitoring_alert_policy" "dlq_messages" {
  for_each = var.enable_monitoring ? local.dlq_subscriptions : {}

  display_name = "DLQ messages accumulating: ${each.key} (${local.environment})"
  combiner     = "OR"
  severity     = "CRITICAL"

  conditions {
    display_name = "Unacked DLQ messages > 0 for 15 min"

    condition_threshold {
      filter          = <<-EOT
        resource.type = "pubsub_subscription"
        AND resource.labels.subscription_id = "${each.key}-dlq-sub"
        AND metric.type = "pubsub.googleapis.com/subscription/num_undelivered_messages"
      EOT
      comparison      = "COMPARISON_GT"
      threshold_value = 0
      duration        = "900s"

      aggregations {
        alignment_period   = "300s"
        per_series_aligner = "ALIGN_MEAN"
      }
    }
  }

  notification_channels = local.notification_channels

  documentation {
    content   = <<-EOT
      ## DLQ messages accumulating

      **Subscription**: ${each.key}-dlq-sub
      **Environment**: ${local.environment}

      Messages have been sitting in the dead-letter queue for more than 15 minutes.
      This means event processing is failing repeatedly.

      ### Response

      1. Follow the [DLQ Triage Runbook](https://github.com/your-org/evidara/blob/main/docs/runbooks/dlq-triage-and-replay.md)
      2. Check Cloud Logging for the consumer service that owns this subscription
      3. Classify the failure (transient vs permanent)
      4. Fix root cause, then replay
    EOT
    mime_type = "text/markdown"
  }

  alert_strategy {
    auto_close = "86400s"
  }
}

# --- Tier 1: Cloud Run error rate (> 5% for 5 minutes) ---

resource "google_monitoring_alert_policy" "cloud_run_error_rate" {
  for_each = var.enable_monitoring ? local.cloud_run_services : {}

  display_name = "High error rate: ${each.key} (${local.environment})"
  combiner     = "OR"
  severity     = "CRITICAL"

  conditions {
    display_name = "5xx error rate > 5% for 5 min"

    condition_threshold {
      filter          = <<-EOT
        resource.type = "cloud_run_revision"
        AND resource.labels.service_name = "${each.value.prefixed_name}"
        AND metric.type = "run.googleapis.com/request_count"
        AND metric.labels.response_code_class = "5xx"
      EOT
      comparison      = "COMPARISON_GT"
      threshold_value = 5
      duration        = "300s"

      aggregations {
        alignment_period     = "60s"
        per_series_aligner   = "ALIGN_RATE"
        cross_series_reducer = "REDUCE_SUM"
      }

      denominator_filter = <<-EOT
        resource.type = "cloud_run_revision"
        AND resource.labels.service_name = "${each.value.prefixed_name}"
        AND metric.type = "run.googleapis.com/request_count"
      EOT

      denominator_aggregations {
        alignment_period     = "60s"
        per_series_aligner   = "ALIGN_RATE"
        cross_series_reducer = "REDUCE_SUM"
      }
    }
  }

  notification_channels = local.notification_channels

  documentation {
    content   = <<-EOT
      ## High error rate

      **Service**: ${each.key} (${each.value.prefixed_name})
      **Environment**: ${local.environment}

      The 5xx error rate has exceeded 5% for more than 5 minutes.

      ### Response

      1. Check Cloud Run logs for the failing service
      2. Look for common patterns: OOM, timeout, dependency failures
      3. Check recent deployments — consider rollback if a new revision caused this
      4. Verify external dependencies (Postgres, OpenSearch, Pub/Sub, Firecrawl)
    EOT
    mime_type = "text/markdown"
  }

  alert_strategy {
    auto_close = "3600s"
  }
}

# --- Tier 2: Cloud Run latency p95 (> 5s for 15 minutes) ---

resource "google_monitoring_alert_policy" "cloud_run_latency" {
  for_each = var.enable_monitoring ? {
    for name, service in local.cloud_run_services :
    name => service
    if contains(["platform-control-api", "legal-search-api"], name)
  } : {}

  display_name = "High latency p95: ${each.key} (${local.environment})"
  combiner     = "OR"
  severity     = "WARNING"

  conditions {
    display_name = "Request latency p95 > 5s for 15 min"

    condition_threshold {
      filter          = <<-EOT
        resource.type = "cloud_run_revision"
        AND resource.labels.service_name = "${each.value.prefixed_name}"
        AND metric.type = "run.googleapis.com/request_latencies"
      EOT
      comparison      = "COMPARISON_GT"
      threshold_value = 5000
      duration        = "900s"

      aggregations {
        alignment_period     = "300s"
        per_series_aligner   = "ALIGN_PERCENTILE_95"
        cross_series_reducer = "REDUCE_MAX"
      }
    }
  }

  notification_channels = local.notification_channels

  documentation {
    content   = <<-EOT
      ## High latency

      **Service**: ${each.key} (${each.value.prefixed_name})
      **Environment**: ${local.environment}

      P95 request latency has exceeded 5 seconds for 15 minutes.

      ### Response

      1. Check for resource contention (CPU, memory)
      2. Review slow database queries
      3. Check OpenSearch cluster health
      4. Consider scaling up instance count or resources
    EOT
    mime_type = "text/markdown"
  }

  alert_strategy {
    auto_close = "3600s"
  }
}
