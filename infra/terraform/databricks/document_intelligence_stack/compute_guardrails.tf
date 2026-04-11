# --------------------------------------------------------------------------
# Databricks compute guardrails — optional cluster policy
#
# Caps per-cluster workers and DBU/hour. Policies do not apply until a
# cluster or job selects this policy (set policy_id on new_cluster in jobs
# or pick the policy in the UI). CAN_USE is granted to the configured
# workspace group so members may attach the policy to clusters they create.
# --------------------------------------------------------------------------

locals {
  # Workspace-scoped name; keep in sync with document-intelligence/databricks.yml
  # variable compute_guardrails_policy_id.lookup.cluster_policy.
  compute_guardrails_cluster_policy_display_name = "Evidara compute guardrails"

  databricks_cluster_policy_definition = jsonencode({
    "dbus_per_hour" : {
      "type" : "range",
      "maxValue" : var.databricks_guardrails_max_dbu_per_hour
    },
    "autoscale.max_workers" : {
      "type" : "range",
      "maxValue" : var.databricks_guardrails_max_workers,
      "isOptional" : true
    },
    "num_workers" : {
      "type" : "range",
      "maxValue" : var.databricks_guardrails_max_workers,
      "isOptional" : true
    }
  })
}

resource "databricks_cluster_policy" "compute_guardrails" {
  count = var.enable_databricks_compute_guardrails ? 1 : 0

  name = local.compute_guardrails_cluster_policy_display_name
  definition = (
    var.databricks_guardrails_cluster_policy_definition_override != null
    ? var.databricks_guardrails_cluster_policy_definition_override
    : local.databricks_cluster_policy_definition
  )
}

resource "databricks_permissions" "compute_guardrails_cluster_policy" {
  count = var.enable_databricks_compute_guardrails ? 1 : 0

  cluster_policy_id = databricks_cluster_policy.compute_guardrails[0].id

  access_control {
    group_name       = var.databricks_guardrails_grant_can_use_group
    permission_level = "CAN_USE"
  }
}
