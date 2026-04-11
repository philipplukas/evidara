variable "environment" {
  description = "Target Evidara environment."
  type        = string

  validation {
    condition     = contains(["dev", "staging", "prod"], lower(var.environment))
    error_message = "environment must be one of dev, staging, or prod."
  }
}

variable "workspace_host" {
  description = "Databricks workspace host URL."
  type        = string
}

variable "catalog_name" {
  description = "Optional Unity Catalog catalog override. Defaults to an environment-specific Evidara catalog name."
  type        = string
  default     = null
  nullable    = true
}

variable "schema_name" {
  description = "Optional schema override. Defaults to published."
  type        = string
  default     = null
  nullable    = true
}

variable "schema_comment" {
  description = "Optional schema description override."
  type        = string
  default     = null
  nullable    = true
}

variable "external_location_name" {
  description = "Optional external location name override. Defaults to an environment-specific Evidara name."
  type        = string
  default     = null
  nullable    = true
}

variable "external_location_url" {
  description = "External location URL backing the published surfaces root, for example gs://bucket/path."
  type        = string
}

variable "storage_credential_name" {
  description = "Existing Unity Catalog storage credential used by the external location."
  type        = string
}

variable "create_external_location" {
  description = "Whether Terraform should create the external location object."
  type        = bool
  default     = true
}

variable "catalog_grants" {
  description = "Principals and privileges to grant on the catalog."
  type = list(object({
    principal  = string
    privileges = list(string)
  }))
  default = []
}

variable "schema_grants" {
  description = "Principals and privileges to grant on the schema."
  type = list(object({
    principal  = string
    privileges = list(string)
  }))
  default = []
}

variable "external_location_grants" {
  description = "Principals and privileges to grant on the external location."
  type = list(object({
    principal  = string
    privileges = list(string)
  }))
  default = []
}

# --- Optional compute guardrails (see compute_guardrails.tf) ---

variable "enable_databricks_compute_guardrails" {
  description = "When true, create a workspace cluster policy with DBU/hour and worker caps, and grant CAN_USE to the configured group."
  type        = bool
  default     = false
}

variable "databricks_guardrails_max_workers" {
  description = "Maximum workers (fixed or autoscale) allowed by the guardrails cluster policy."
  type        = number
  default     = 8

  validation {
    condition     = var.databricks_guardrails_max_workers >= 1
    error_message = "databricks_guardrails_max_workers must be at least 1."
  }
}

variable "databricks_guardrails_max_dbu_per_hour" {
  description = "Maximum DBU per hour per cluster enforced by the guardrails policy."
  type        = number
  default     = 25

  validation {
    condition     = var.databricks_guardrails_max_dbu_per_hour > 0
    error_message = "databricks_guardrails_max_dbu_per_hour must be positive."
  }
}

variable "databricks_guardrails_grant_can_use_group" {
  description = "Workspace group that may attach the guardrails cluster policy (typically \"users\")."
  type        = string
  default     = "users"
}

variable "databricks_guardrails_cluster_policy_definition_override" {
  description = "Optional raw JSON policy definition; when null, a default policy is built from the max_workers and max_dbu_per_hour variables."
  type        = string
  default     = null
  nullable    = true
}
