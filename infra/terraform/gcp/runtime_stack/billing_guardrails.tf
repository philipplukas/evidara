# --------------------------------------------------------------------------
# Billing guardrails — optional project-scoped Cloud Billing budget
#
# Alerts at configured fractions of a fixed monthly amount for *this*
# GCP project only. Budgets notify; they do not stop usage.
#
# Threshold alerts go to billing account admins by default. When
# billing_budget_notification_emails is non-empty, an all_updates_rule
# adds Cloud Monitoring email channels (and optionally project Owners).
# If you disable default IAM recipients, you must list at least one email
# (see variable validation).
#
# IAM: principal applying Terraform needs a role that can create budgets on
# the billing account (for example Billing Account Administrator or a
# custom role including billing.budgets.create).
# --------------------------------------------------------------------------

resource "google_monitoring_notification_channel" "billing_budget_email" {
  for_each = var.enable_billing_budget ? toset(var.billing_budget_notification_emails) : []

  project      = var.project_id
  display_name = substr("Budget alerts: ${each.key} (${local.environment})", 0, 1024)
  type         = "email"
  labels = {
    email_address = each.key
  }
}

resource "google_billing_budget" "project_spend" {
  count = var.enable_billing_budget ? 1 : 0

  billing_account = var.billing_account_id
  # display_name must be <= 60 characters (GCP API).
  display_name = substr("Evidara-${local.environment}-${var.project_id}", 0, 60)

  budget_filter {
    # Billing budget filters expect projects/{project_number} (see GCP docs).
    projects = ["projects/${local.effective_project_number}"]
  }

  amount {
    specified_amount {
      currency_code = var.billing_budget_currency_code
      units           = var.billing_budget_amount_units
    }
  }

  dynamic "threshold_rules" {
    for_each = var.billing_budget_threshold_percentages
    content {
      threshold_percent = threshold_rules.value
      spend_basis       = "CURRENT_SPEND"
    }
  }

  # Provider maps this to the API notificationsRule. At least one of
  # monitoring_notification_channels or pubsub_topic is required when this
  # block is present; omit it to rely on default billing-account recipients only.
  dynamic "all_updates_rule" {
    for_each = length(var.billing_budget_notification_emails) > 0 ? [1] : []
    content {
      schema_version                   = "1.0"
      disable_default_iam_recipients   = var.billing_budget_disable_default_iam_recipients
      monitoring_notification_channels = [for ch in google_monitoring_notification_channel.billing_budget_email : ch.id]
      enable_project_level_recipients  = var.billing_budget_enable_project_level_recipients
    }
  }
}

check "billing_budget_requires_billing_account" {
  assert {
    condition     = !var.enable_billing_budget || length(var.billing_account_id) > 0
    error_message = "When enable_billing_budget is true, billing_account_id must be set (Billing → Account management in Cloud Console)."
  }
}

check "billing_budget_has_recipients_when_default_disabled" {
  assert {
    condition = (
      !var.enable_billing_budget
      || !var.billing_budget_disable_default_iam_recipients
      || length(var.billing_budget_notification_emails) > 0
    )
    error_message = "When enable_billing_budget is true and billing_budget_disable_default_iam_recipients is true, set billing_budget_notification_emails so alerts have a recipient."
  }
}
